import difflib

from django.core.mail import send_mass_mail
from django.db.models import Q
from django.http import HttpResponseBadRequest, HttpResponseNotAllowed
from django.shortcuts import render, redirect, get_object_or_404
from django.template import Context, Template
from django.views.decorators.http import require_POST

from account.decorators import login_required

# @@@ switch to pinax-teams
from symposion.teams.models import Team

from symposion.conf import settings
from symposion.proposals.models import ProposalBase, ProposalSection
from symposion.utils.mail import send_email

from symposion.reviews.forms import ReviewForm, SpeakerCommentForm
from symposion.reviews.forms import BulkPresentationForm
from symposion.reviews.models import (
    ReviewAssignment, Review, LatestVote, ProposalResult, NotificationTemplate,
    ResultNotification
)
from symposion.utils import anonymous_review


def access_not_permitted(request):
    return render(request, "symposion/reviews/access_not_permitted.html")


def proposals_generator(request, queryset, user_pk=None, check_speaker=True):

    for obj in queryset:
        # @@@ this sucks; we can do better
        if check_speaker:
            if request.user in [s.user for s in obj.speakers()]:
                continue

        try:
            obj.result
        except ProposalResult.DoesNotExist:
            ProposalResult.objects.get_or_create(proposal=obj)

        obj.comment_count = obj.result.comment_count
        obj.score = obj.result.score
        obj.total_votes = obj.result.vote_count
        obj.strong_accept = obj.result.strong_accept
        obj.weak_accept = obj.result.weak_accept
        obj.weak_reject = obj.result.weak_reject
        obj.strong_reject = obj.result.strong_reject
        lookup_params = dict(proposal=obj)

        if user_pk:
            lookup_params["user__pk"] = user_pk
        else:
            lookup_params["user"] = request.user

        try:
            obj.user_vote = LatestVote.objects.get(**lookup_params).vote
            obj.user_vote_css = LatestVote.objects.get(**lookup_params).css_class()
        except LatestVote.DoesNotExist:
            obj.user_vote = None
            obj.user_vote_css = "no-vote"

        # Anonymize the speakers if we're doing blind review.
        obj = obj.redacted()

        yield obj


# Returns a list of all proposals, proposals reviewed by the user, or the proposals the user has
# yet to review depending on the link user clicks in dashboard
@login_required
def review_section(request, section_slug, assigned=False, reviewed="all"):

    if not request.user.has_perm("symposion_reviews.can_review_%s" % section_slug):
        return access_not_permitted(request)

    section = get_object_or_404(ProposalSection, section__slug=section_slug)
    queryset = ProposalBase.objects.filter(kind__section=section.section)

    if assigned:
        assignments = ReviewAssignment.objects.filter(user=request.user)\
            .values_list("proposal__id")
        queryset = queryset.filter(id__in=assignments)

    # passing reviewed in from reviews.urls and out to review_list for
    # appropriate template header rendering
    if reviewed == "all":
        queryset = queryset.select_related("result").select_subclasses()
        reviewed = "all_reviews"
    elif reviewed == "reviewed":
        queryset = queryset.filter(reviews__user=request.user)
        reviewed = "user_reviewed"
    else:
        queryset = queryset.exclude(reviews__user=request.user).exclude(
            speaker__user=request.user)
        reviewed = "user_not_reviewed"

    queryset = queryset.filter(cancelled=False)
    # Show proposals with least votes first, then by oldest
    queryset = queryset.order_by("result__vote_count", "submitted")

    proposals = proposals_generator(request, queryset)

    ctx = {
        "proposals": proposals,
        "section": section,
        "reviewed": reviewed,
    }

    return render(request, "symposion/reviews/review_list.html", ctx)


@login_required
def review_list(request, section_slug, user_pk):

    # if they're not a reviewer admin and they aren't the person whose
    # review list is being asked for, don't let them in
    if not request.user.has_perm("symposion_reviews.can_manage_%s" % section_slug):
        if not request.user.pk == user_pk:
            return access_not_permitted(request)

    queryset = ProposalBase.objects.select_related("speaker__user", "result")
    reviewed = LatestVote.objects.filter(user__pk=user_pk).values_list("proposal", flat=True)
    queryset = queryset.filter(pk__in=reviewed)
    proposals = queryset.order_by("submitted")

    admin = request.user.has_perm("symposion_reviews.can_manage_%s" % section_slug)

    proposals = proposals_generator(request, proposals, user_pk=user_pk, check_speaker=not admin)

    ctx = {
        "proposals": proposals,
    }
    return render(request, "symposion/reviews/review_list.html", ctx)


@login_required
def review_admin(request, section_slug):

    if not request.user.has_perm("symposion_reviews.can_manage_%s" % section_slug):
        return access_not_permitted(request)

    def reviewers():
        already_seen = set()

        for team in Team.objects.filter(permissions__codename="can_review_%s" % section_slug):
            for membership in team.memberships.filter(Q(state="member") | Q(state="manager")):
                user = membership.user
                if user.pk in already_seen:
                    continue
                already_seen.add(user.pk)

                user.comment_count = Review.objects.filter(user=user).count()
                user.total_votes = LatestVote.objects.filter(user=user).count()
                user.strong_accept = LatestVote.objects.filter(
                    user=user,
                    vote=LatestVote.VOTES.STRONG_ACCEPT
                ).count()
                user.weak_accept = LatestVote.objects.filter(
                    user=user,
                    vote=LatestVote.VOTES.WEAK_ACCEPT
                ).count()
                user.weak_reject = LatestVote.objects.filter(
                    user=user,
                    vote=LatestVote.VOTES.WEAK_REJECT
                ).count()
                user.strong_reject = LatestVote.objects.filter(
                    user=user,
                    vote=LatestVote.VOTES.STRONG_REJECT
                ).count()

                yield user

    ctx = {
        "section_slug": section_slug,
        "reviewers": reviewers(),
    }
    return render(request, "symposion/reviews/review_admin.html", ctx)


# FIXME: This view is too complex according to flake8
@login_required
def review_detail(request, pk):

    proposals = ProposalBase.objects.select_related("result").select_subclasses()
    proposal = get_object_or_404(proposals, pk=pk)

    if not request.user.has_perm("symposion_reviews.can_review_%s" % proposal.kind.section.slug):
        return access_not_permitted(request)

    speakers = [s.user for s in proposal.speakers()]

    if not request.user.is_superuser and request.user in speakers:
        return access_not_permitted(request)

    admin = request.user.is_staff

    try:
        latest_vote = LatestVote.objects.get(proposal=proposal, user=request.user)
    except LatestVote.DoesNotExist:
        latest_vote = None

    if request.method == "POST":
        if request.user in speakers:
            return access_not_permitted(request)

        if "vote_submit" in request.POST:
            review_form = ReviewForm(request.POST)
            if review_form.is_valid():

                review = review_form.save(commit=False)
                review.user = request.user
                review.proposal = proposal
                review.save()

                return redirect(request.path)
            else:
                message_form = SpeakerCommentForm()
        elif "message_submit" in request.POST:
            message_form = SpeakerCommentForm(request.POST)
            if message_form.is_valid():

                message = message_form.save(commit=False)
                message.user = request.user
                message.proposal = proposal
                message.save()

                for speaker in speakers:
                    if speaker and speaker.email:
                        ctx = {
                            "proposal": proposal,
                            "message": message,
                            "reviewer": False,
                        }
                        send_email(
                            [speaker.email], "proposal_new_message",
                            context=ctx
                        )

                return redirect(request.path)
            else:
                initial = {}
                if latest_vote:
                    initial["vote"] = latest_vote.vote
                if request.user in speakers:
                    review_form = None
                else:
                    review_form = ReviewForm(initial=initial)
        elif "result_submit" in request.POST:
            if admin:
                result = request.POST["result_submit"]

                if result == "accept":
                    proposal.result.status = "accepted"
                    proposal.result.save()
                elif result == "reject":
                    proposal.result.status = "rejected"
                    proposal.result.save()
                elif result == "undecide":
                    proposal.result.status = "undecided"
                    proposal.result.save()
                elif result == "standby":
                    proposal.result.status = "standby"
                    proposal.result.save()

            return redirect(request.path)
        elif "update_title" in request.POST:
            if admin:
                action = request.POST["update_title"]
                if action == "Apply":
                    proposal.presentation.title = proposal.title
                    proposal.presentation.save()
                elif action == "Reject":
                    proposal.title = proposal.presentation.title
                    proposal.save()
            return redirect(request.path + '#proposal-updates')
        elif "update_description" in request.POST:
            if admin:
                action = request.POST["update_description"]
                if action == "Apply":
                    proposal.presentation.description = proposal.description
                    proposal.presentation.save()
                elif action == "Reject":
                    proposal.description = proposal.presentation.description
                    proposal.save()
            return redirect(request.path + '#proposal-updates')
        elif "update_abstract" in request.POST:
            if admin:
                action = request.POST["update_abstract"]
                if action == "Apply":
                    proposal.presentation.abstract = proposal.abstract
                    proposal.presentation.save()
                elif action == "Reject":
                    proposal.abstract = proposal.presentation.abstract
                    proposal.save()
            return redirect(request.path + '#proposal-updates')
    else:
        initial = {}
        if latest_vote:
            initial["vote"] = latest_vote.vote
        if request.user in speakers:
            review_form = None
        else:
            review_form = ReviewForm(initial=initial)
        message_form = SpeakerCommentForm()

    proposal.comment_count = proposal.result.comment_count
    proposal.total_votes = proposal.result.vote_count
    proposal.strong_accept = proposal.result.strong_accept
    proposal.weak_accept = proposal.result.weak_accept
    proposal.weak_reject = proposal.result.weak_reject
    proposal.strong_reject = proposal.result.strong_reject

    reviews = Review.objects.filter(proposal=proposal).order_by("-submitted_at")
    messages = proposal.messages.order_by("submitted_at")

    # Anonymize the proposal if needs be.
    proposal = proposal.redacted()

    messages = [anonymous_review.MessageProxy(message) for message in messages]

    changes = {'test': '<b>hi</b>'}
    try:
        presentation = proposal.presentation
        differ = difflib.HtmlDiff()
        if proposal.title != presentation.title:
            changes['title_diff'] = differ.make_table([proposal.title],
                    [presentation.title], 'Proposal', 'Presentation')
        if proposal.abstract != presentation.abstract:
            changes['abstract_diff'] = differ.make_table(
                    proposal.abstract.split('\n'), presentation.abstract.split('\n'), 'Proposal', 'Presentation')
        if proposal.description != presentation.description:
            changes['description_diff'] = differ.make_table(
                    proposal.description.split('\n'), presentation.description.split('\n'), 'Proposal', 'Presentation')
    except:
        # no presentation
        pass

    return render(request, "symposion/reviews/review_detail.html", {
        "proposal": proposal,
        "latest_vote": latest_vote,
        "reviews": reviews,
        "review_messages": messages,
        "review_form": review_form,
        "message_form": message_form,
        "proposal_changes": changes,
    })


@login_required
@require_POST
def review_delete(request, pk):
    review = get_object_or_404(Review, pk=pk)
    section_slug = review.section.slug

    if not request.user.has_perm("symposion_reviews.can_manage_%s" % section_slug):
        return access_not_permitted(request)

    review = get_object_or_404(Review, pk=pk)
    review.delete()

    return redirect("review_detail", pk=review.proposal.pk)


@login_required
def review_status(request, section_slug=None, key=None):

    if not request.user.has_perm("symposion_reviews.can_review_%s" % section_slug):
        return access_not_permitted(request)

    VOTE_THRESHOLD = settings.SYMPOSION_VOTE_THRESHOLD

    ctx = {
        "section_slug": section_slug,
        "vote_threshold": VOTE_THRESHOLD,
    }

    queryset = ProposalBase.objects.select_related("speaker__user", "result").select_subclasses()
    if section_slug:
        queryset = queryset.filter(kind__section__slug=section_slug)

    proposals = {
        # proposals with at least VOTE_THRESHOLD reviews and at least one ++ and no --s, sorted by
        # the 'score'
        "positive": queryset.filter(result__vote_count__gte=VOTE_THRESHOLD, result__strong_accept__gt=0,
                                    result__strong_reject=0).order_by("-result__score"),
        # proposals with at least VOTE_THRESHOLD reviews and at least one -- and no ++s, reverse
        # sorted by the 'score'
        "negative": queryset.filter(result__vote_count__gte=VOTE_THRESHOLD, result__strong_reject__gt=0,
                                    result__strong_accept=0).order_by("result__score"),
        # proposals with at least VOTE_THRESHOLD reviews and neither a ++ or a --, sorted by total
        # votes (lowest first)
        "indifferent": queryset.filter(result__vote_count__gte=VOTE_THRESHOLD, result__strong_reject=0,
                                       result__strong_accept=0).order_by("result__vote_count"),
        # proposals with at least VOTE_THRESHOLD reviews and both a ++ and --, sorted by total
        # votes (highest first)
        "controversial": queryset.filter(result__vote_count__gte=VOTE_THRESHOLD,
                                         result__strong_accept__gt=0, result__strong_reject__gt=0)
        .order_by("-result__vote_count"),
        # proposals with fewer than VOTE_THRESHOLD reviews
        "too_few": queryset.filter(result__vote_count__lt=VOTE_THRESHOLD)
        .order_by("result__vote_count"),
    }

    admin = request.user.has_perm("symposion_reviews.can_manage_%s" % section_slug)

    for status in proposals:
        if key and key != status:
            continue
        proposals[status] = list(proposals_generator(request, proposals[status], check_speaker=not admin))

    if key:
        ctx.update({
            "key": key,
            "proposals": proposals[key],
        })
    else:
        ctx["proposals"] = proposals

    return render(request, "symposion/reviews/review_stats.html", ctx)


@login_required
def review_assignments(request):
    if not request.user.groups.filter(name="reviewers").exists():
        return access_not_permitted(request)
    assignments = ReviewAssignment.objects.filter(
        user=request.user,
        opted_out=False
    )
    return render(request, "symposion/reviews/review_assignment.html", {
        "assignments": assignments,
    })


@login_required
@require_POST
def review_assignment_opt_out(request, pk):
    review_assignment = get_object_or_404(
        ReviewAssignment, pk=pk, user=request.user)
    if not review_assignment.opted_out:
        review_assignment.opted_out = True
        review_assignment.save()
        ReviewAssignment.create_assignments(
            review_assignment.proposal, origin=ReviewAssignment.AUTO_ASSIGNED_LATER)
    return redirect("review_assignments")


@login_required
def review_bulk_accept(request, section_slug):
    if not request.user.has_perm("symposion_reviews.can_manage_%s" % section_slug):
        return access_not_permitted(request)
    if request.method == "POST":
        form = BulkPresentationForm(request.POST)
        if form.is_valid():
            talk_ids = form.cleaned_data["talk_ids"].split(",")
            talks = ProposalBase.objects.filter(id__in=talk_ids).select_related("result")
            for talk in talks:
                talk.result.status = "accepted"
                talk.result.save()
            return redirect("review_section", section_slug=section_slug)
    else:
        form = BulkPresentationForm()

    return render(request, "symposion/reviews/review_bulk_accept.html", {
        "form": form,
    })


@login_required
def result_notification(request, section_slug, status):
    if not request.user.has_perm("symposion_reviews.can_manage_%s" % section_slug):
        return access_not_permitted(request)

    proposals = ProposalBase.objects.filter(kind__section__slug=section_slug, result__status=status).select_related("speaker__user", "result").select_subclasses()
    notification_templates = NotificationTemplate.objects.all()

    ctx = {
        "section_slug": section_slug,
        "status": status,
        "proposals": [proposal.redacted() for proposal in proposals],
        "notification_templates": notification_templates,
    }
    return render(request, "symposion/reviews/result_notification.html", ctx)


@login_required
def result_notification_prepare(request, section_slug, status):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    if not request.user.has_perm("symposion_reviews.can_manage_%s" % section_slug):
        return access_not_permitted(request)

    proposal_pks = []
    try:
        for pk in request.POST.getlist("_selected_action"):
            proposal_pks.append(int(pk))
    except ValueError:
        return HttpResponseBadRequest()
    proposals = ProposalBase.objects.filter(
        kind__section__slug=section_slug,
        result__status=status,
    )
    proposals = proposals.filter(pk__in=proposal_pks)
    proposals = proposals.select_related("speaker__user", "result")
    proposals = proposals.select_subclasses()

    notification_template_pk = request.POST.get("notification_template", "")
    if notification_template_pk:
        notification_template = NotificationTemplate.objects.get(pk=notification_template_pk)
    else:
        notification_template = None

    ctx = {
        "section_slug": section_slug,
        "status": status,
        "notification_template": notification_template,
        "proposals": proposals,
        "proposal_pks": ",".join([str(pk) for pk in proposal_pks]),
    }
    return render(request, "symposion/reviews/result_notification_prepare.html", ctx)


@login_required
def result_notification_send(request, section_slug, status):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    if not request.user.has_perm("symposion_reviews.can_manage_%s" % section_slug):
        return access_not_permitted(request)

    if not all([k in request.POST for k in ["proposal_pks", "from_address", "subject", "body"]]):
        return HttpResponseBadRequest()

    try:
        proposal_pks = [int(pk) for pk in request.POST["proposal_pks"].split(",")]
    except ValueError:
        return HttpResponseBadRequest()

    proposals = ProposalBase.objects.filter(
        kind__section__slug=section_slug,
        result__status=status,
    )
    proposals = proposals.filter(pk__in=proposal_pks)
    proposals = proposals.select_related("speaker__user", "result")
    proposals = proposals.select_subclasses()

    notification_template_pk = request.POST.get("notification_template", "")
    if notification_template_pk:
        notification_template = NotificationTemplate.objects.get(pk=notification_template_pk)
    else:
        notification_template = None

    emails = []

    for proposal in proposals:
        rn = ResultNotification()
        rn.proposal = proposal
        rn.template = notification_template
        rn.to_address = proposal.speaker_email
        rn.from_address = request.POST["from_address"]
        proposal_context = proposal.notification_email_context()
        rn.subject = Template(request.POST["subject"]).render(
            Context({
                "proposal": proposal_context
            })
        )
        rn.body = Template(request.POST["body"]).render(
            Context({
                "proposal": proposal_context
            })
        )
        rn.save()
        emails.append(rn.email_args)

    send_mass_mail(emails)

    return redirect("result_notification", section_slug=section_slug, status=status)
