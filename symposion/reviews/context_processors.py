from symposion.proposals.models import ProposalSection


def reviews(request):
    sections = []
    for section in ProposalSection.objects.all().order_by('section__name'):
        if request.user.has_perm("symposion_reviews.can_review_%s" % section.section.slug):
            sections.append(section)
    return {
        "review_sections": sections,
    }
