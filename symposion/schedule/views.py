from __future__ import unicode_literals
import hashlib
import json

from django.core.urlresolvers import reverse
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.template import loader, Context

from django.contrib.auth.models import User
from django.contrib import messages
from django.contrib.sites.models import Site

from account.decorators import login_required

from symposion.schedule.forms import SlotEditForm, ScheduleSectionForm
from symposion.schedule.models import Schedule, Day, Slot, Presentation, Session, SessionRole
from symposion.schedule.timetable import TimeTable

# FIXME: It is bad that I'm importing this and I feel bad:
from pinaxcon.proposals.models import ConferenceSpeaker, ConferenceSpeakerOrganizerRoles


def fetch_schedule(slug):
    qs = Schedule.objects.all()

    if slug is None:
        if qs.count() > 1:
            raise Http404()
        schedule = next(iter(qs), None)
        if schedule is None:
            raise Http404()
    else:
        schedule = get_object_or_404(qs, section__slug=slug)

    return schedule


def schedule_conference(request):

    sections = []

    if request.user.is_staff:
        section_days = Day.objects.filter(
                schedule__hidden=False).order_by('date')
    else:
        section_days = Day.objects.filter(schedule__hidden=False,
                schedule__published=True).order_by('date')

    for sd in section_days:
        days = [TimeTable(sd)]
        sections.append({
            "schedule": sd.schedule,
            "days": days,
            })

    ctx = {
        "sections": sections,
    }
    return render(request, "symposion/schedule/schedule_conference.html", ctx)


def schedule_detail(request, slug=None):

    schedule = fetch_schedule(slug)
    if not schedule.published and not request.user.is_staff:
        raise Http404()

    days_qs = Day.objects.filter(schedule=schedule)
    days = [TimeTable(day) for day in days_qs]

    ctx = {
        "schedule": schedule,
        "days": days,
    }
    return render(request, "symposion/schedule/schedule_detail.html", ctx)


def schedule_list(request, slug=None):
    schedule = fetch_schedule(slug)
    if not schedule.published and not request.user.is_staff:
        raise Http404()

    presentations = Presentation.objects.filter(section=schedule.section)
    presentations = presentations.exclude(cancelled=True).order_by("title")

    ctx = {
        "schedule": schedule,
        "presentations": presentations,
    }
    return render(request, "symposion/schedule/schedule_list.html", ctx)

def _speaker_data(speaker, extras=None):
    if extras is None:
        extras = {}
    data = {
        "speaker_id": speaker.id,
        "biography": speaker.biography,
        "biography_html": speaker.biography_html,
        "name": speaker.name,
    }
    try:
        data["photo"] = {
            "description": speaker.name,
            "url": speaker.photo.url
        }
    except ValueError:
        speaker_hash = hashlib.md5(speaker.email).hexdigest()
        gravatar_url = "https://www.gravatar.com/avatar/{}?s=250&r=g&d=http%3A%2F%2Fstatic-cfp.pyohio.org%2Fspeaker_photo%2Fdefault.png".format(speaker_hash)
        data["photo"] = {
            "description": speaker.name,
            "url": gravatar_url,
        }
    try:
        # Reaching into the app to get extra speaker data for now:
        full_speaker = ConferenceSpeaker.objects.get(speakerbase_ptr=speaker)
        data["twitter"] = full_speaker.twitter_username
    except:
        data["twitter"] = ''
    data.update(extras)
    return data

def _presentation_data(presentation):
    from pprint import pprint
    speakers_data = [_speaker_data(presentation.speaker)]
    additional_speakers = [_speaker_data(s) for s in presentation.proposal.additional_speakers.all()]
    speakers_data.extend(additional_speakers)
    data = {
        "presentation_id": presentation.id,
        "title": presentation.title,
        "abstract": presentation.abstract,
        "abstract_html": presentation.abstract_html,
        "description": presentation.description,
        "description_html": presentation.description_html,
        "kind": str(presentation.proposal.kind),
        "speakers": speakers_data
    }
    if hasattr(presentation.proposal, "prerequisite_setup_html"):
        data["prerequisite_setup_html"] = presentation.proposal.prerequisite_setup_html
    
    if presentation.slot is None:
        schedule = {
            "start": 'start TBD',
            "end": 'end TBD',
            "room": 'room TBD',
            }
    else:
        schedule = {
            "start": presentation.slot.start_datetime.isoformat(),
            "end": presentation.slot.end_datetime.isoformat(),
            "room": presentation.slot.room_names,
        }
    data["schedule"] = schedule
    return data

def _presentation_summary(presentation):
    data = {
        "presentation_id": presentation.id,
        "title": presentation.title,
        "kind": str(presentation.proposal.kind),
    }
    return data

def schedule_list_json(request, slug=None):
    schedule = fetch_schedule(slug)
    if not schedule.published and not request.user.is_staff:
        raise Http404()

    presentations = Presentation.objects.filter(section=schedule.section)
    presentations = presentations.exclude(cancelled=True).order_by("title")

    all_data = [_presentation_data(p) for p in presentations]

    return JsonResponse(all_data, safe=False)

def _get_presentations_from_section(section_slug):
    schedule = fetch_schedule(section_slug)
    presentations = Presentation.objects.filter(section=schedule.section)
    presentations = presentations.exclude(cancelled=True).order_by("title")
    return presentations


def speaker_list_json(request):
    # TODO: refactor this mess
    talks = _get_presentations_from_section('talks')
    tutorials = _get_presentations_from_section('tutorials')
    all_sessions = list(talks) + list(tutorials)
    all_speakers = set()
    speaker_sessions = {}
    for session in all_sessions:
        all_speakers.add(session.speaker)
        if session.speaker.id in speaker_sessions:
            speaker_sessions[session.speaker.id].append(session)
        else:
            speaker_sessions[session.speaker.id] = [session]
        for speaker in session.proposal.additional_speakers.all():
            all_speakers.add(speaker)
            if speaker.id in speaker_sessions:
                speaker_sessions[speaker.id].append(session)
            else:
                speaker_sessions[speaker.id] = [session]
    speakers_data = [_speaker_data(s) for s in list(all_speakers)]
    for speaker_data in speakers_data:
        speaker_data['presentations'] = [_presentation_summary(p) for p in speaker_sessions[speaker_data['speaker_id']]]
    return JsonResponse(speakers_data, safe=False)


def organizer_list_json(request):
    csors = ConferenceSpeakerOrganizerRoles.objects.order_by('roles')
    speaker_roles = []
    for csor in csors:
        current_roles = (csor.speaker, [r.title for r in csor.roles.all()])
        if current_roles not in speaker_roles:
            speaker_roles.append(current_roles)

    organizer_data = [_speaker_data(s[0], extras={'organizer_roles': s[1]}) for s in speaker_roles]
    return JsonResponse(organizer_data, safe=False)

def slots_list_json(request):
    return JsonResponse(_slots_json(request), safe=False)

def _slots_json(request):
    slots = Slot.objects.filter(
        day__schedule__published=True,
        day__schedule__hidden=False
    ).order_by("start")

    data = []

    for slot in slots:
        slot_data = {
            "room": ", ".join(room["name"] for room in slot.rooms.order_by('order').values()),
            "rooms": [room["name"] for room in slot.rooms.order_by('order').values()],
            "room_order": min([room["order"] for room in slot.rooms.values()]),
            "start": slot.start_datetime.isoformat(),
            "end": slot.end_datetime.isoformat(),
            "duration": slot.length_in_minutes,
            "kind": slot.kind.label,
            "section": slot.day.schedule.section.slug,
            "slot_id": slot.pk,
            "title": "Presentation TBD",
            "speaker_name": None,
            "speakers": None,
            "description_html": None,
            "cancelled": False,
            "presentation_id": None,
        }
        if hasattr(slot.content, "proposal"):
            slot_data.update({
                "title": slot.content.title,
                "speaker_name": ", ".join([s.name for s in slot.content.speakers()]),
                "speakers": [{'name': s.name, 'speaker_id': s.id} for s in slot.content.speakers()],
                "description_html": slot.content.description_html,
                "cancelled": slot.content.cancelled,
                "presentation_id": slot.content.id,
            })
        else:
            slot_data.update({
                "title": slot.content_override if slot.content_override else "Presentation TBD",
            })
        data.append(slot_data)
    return data



def schedule_list_csv(request, slug=None):
    schedule = fetch_schedule(slug)
    if not schedule.published and not request.user.is_staff:
        raise Http404()

    presentations = Presentation.objects.filter(section=schedule.section)
    presentations = presentations.exclude(cancelled=True).order_by("id")
    response = HttpResponse(content_type="text/csv")

    if slug:
        file_slug = slug
    else:
        file_slug = "presentations"
    response["Content-Disposition"] = 'attachment; filename="%s.csv"' % file_slug

    response.write(loader.get_template("symposion/schedule/schedule_list.csv").render(Context({
        "presentations": presentations,

    })))
    return response


@login_required
def schedule_edit(request, slug=None):

    if not request.user.is_staff:
        raise Http404()

    schedule = fetch_schedule(slug)

    if request.method == "POST":
        form = ScheduleSectionForm(
            request.POST, request.FILES, schedule=schedule
        )
        if form.is_valid():
            if 'submit' in form.data:
                msg = form.build_schedule()
            elif 'delete' in form.data:
                msg = form.delete_schedule()
            messages.add_message(request, msg[0], msg[1])
    else:
        form = ScheduleSectionForm(schedule=schedule)
    days_qs = Day.objects.filter(schedule=schedule)
    days = [TimeTable(day) for day in days_qs]
    ctx = {
        "schedule": schedule,
        "days": days,
        "form": form
    }
    return render(request, "symposion/schedule/schedule_edit.html", ctx)


@login_required
def schedule_slot_edit(request, slug, slot_pk):

    if not request.user.is_staff:
        raise Http404()

    slot = get_object_or_404(Slot, day__schedule__section__slug=slug, pk=slot_pk)

    if request.method == "POST":
        form = SlotEditForm(request.POST, slot=slot)
        if form.is_valid():
            save = False
            if "content_override" in form.cleaned_data:
                slot.content_override = form.cleaned_data["content_override"]
                save = True
            if "presentation" in form.cleaned_data:
                presentation = form.cleaned_data["presentation"]
                if presentation is None:
                    slot.unassign()
                else:
                    slot.assign(presentation)
            if save:
                slot.save()
        return redirect("schedule_edit", slug)
    else:
        form = SlotEditForm(slot=slot)
        ctx = {
            "slug": slug,
            "form": form,
            "slot": slot,
        }
        return render(request, "symposion/schedule/_slot_edit.html", ctx)


def schedule_presentation_detail(request, pk):

    presentation = get_object_or_404(Presentation, pk=pk)
    if presentation.slot:
        schedule = presentation.slot.day.schedule
        if not schedule.published and not request.user.is_staff:
            raise Http404()
    else:
        schedule = None

    ctx = {
        "presentation": presentation,
        "schedule": schedule,
    }
    return render(request, "symposion/schedule/presentation_detail.html", ctx)


def schedule_json(request):
    return HttpResponse(
        json.dumps({"schedule": _schedule_json(request)}),
        content_type="application/json"
    )

def _schedule_json(request):
    ''' Produce the dictionary object for jsonifying '''

    slots = Slot.objects.filter(
        day__schedule__published=True,
        day__schedule__hidden=False
    ).order_by("start")

    protocol = request.META.get('HTTP_X_FORWARDED_PROTO', 'http')
    data = []

    for slot in slots:
        slot_data = {
            "room": ", ".join(room["name"] for room in slot.rooms.values()),
            "rooms": [room["name"] for room in slot.rooms.values()],
            "start": slot.start_datetime.isoformat(),
            "end": slot.end_datetime.isoformat(),
            "duration": slot.length_in_minutes,
            "kind": slot.kind.label,
            "section": slot.day.schedule.section.slug,
            "conf_key": slot.pk,
            # TODO: models should be changed.
            # these are model features from other conferences that have forked symposion
            # these have been used almost everywhere and are good candidates for
            # base proposals
            "license": "CC BY",
            "tags": "",
            "released": True,
            "contact": [],
        }
        if hasattr(slot.content, "proposal"):
            slot_data.update({
                "name": slot.content.title,
                "authors": [s.name for s in slot.content.speakers()],
                "contact": [
                    s.email for s in slot.content.speakers()
                ] if request.user.is_staff else ["redacted"],
                "abstract": slot.content.abstract,
                "description": slot.content.description,
                "conf_url": "https://www.pyohio.org/2019/presentations/%s" % (slot.content.id),
                "cancelled": slot.content.cancelled,
            })
        else:
            slot_data.update({
                "name": slot.content_override if slot.content_override else "Slot",
            })
        data.append(slot_data)

    return data


def session_list(request):
    sessions = Session.objects.all().order_by('pk')

    return render(request, "symposion/schedule/session_list.html", {
        "sessions": sessions,
    })


@login_required
def session_staff_email(request):

    if not request.user.is_staff:
        return redirect("schedule_session_list")

    data = "\n".join(user.email for user in User.objects.filter(sessionrole__isnull=False).distinct())

    return HttpResponse(data, content_type="text/plain;charset=UTF-8")


def session_detail(request, session_id):

    session = get_object_or_404(Session, id=session_id)

    chair = None
    chair_denied = False
    chairs = SessionRole.objects.filter(session=session, role=SessionRole.SESSION_ROLE_CHAIR).exclude(status=False)
    if chairs:
        chair = chairs[0].user
    else:
        if request.user.is_authenticated():
            # did the current user previously try to apply and got rejected?
            if SessionRole.objects.filter(session=session, user=request.user, role=SessionRole.SESSION_ROLE_CHAIR, status=False):
                chair_denied = True

    runner = None
    runner_denied = False
    runners = SessionRole.objects.filter(session=session, role=SessionRole.SESSION_ROLE_RUNNER).exclude(status=False)
    if runners:
        runner = runners[0].user
    else:
        if request.user.is_authenticated():
            # did the current user previously try to apply and got rejected?
            if SessionRole.objects.filter(session=session, user=request.user, role=SessionRole.SESSION_ROLE_RUNNER, status=False):
                runner_denied = True

    if request.method == "POST" and request.user.is_authenticated():
        if not hasattr(request.user, "profile") or not request.user.profile.is_complete:
            response = redirect("profile_edit")
            response["Location"] += "?next=%s" % request.path
            return response

        role = request.POST.get("role")
        if role == "chair":
            if chair is None and not chair_denied:
                SessionRole(session=session, role=SessionRole.SESSION_ROLE_CHAIR, user=request.user).save()
        elif role == "runner":
            if runner is None and not runner_denied:
                SessionRole(session=session, role=SessionRole.SESSION_ROLE_RUNNER, user=request.user).save()
        elif role == "un-chair":
            if chair == request.user:
                session_role = SessionRole.objects.filter(session=session, role=SessionRole.SESSION_ROLE_CHAIR, user=request.user)
                if session_role:
                    session_role[0].delete()
        elif role == "un-runner":
            if runner == request.user:
                session_role = SessionRole.objects.filter(session=session, role=SessionRole.SESSION_ROLE_RUNNER, user=request.user)
                if session_role:
                    session_role[0].delete()

        return redirect("schedule_session_detail", session_id)

    return render(request, "symposion/schedule/session_detail.html", {
        "session": session,
        "chair": chair,
        "chair_denied": chair_denied,
        "runner": runner,
        "runner_denied": runner_denied,
    })

