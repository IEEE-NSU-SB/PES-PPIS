from django.db import models


class EventFormStatus(models.Model):
    """Control publish/unpublish of the registration form"""
    is_published = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Event Form Status"

    def __str__(self):
        return "Published" if self.is_published else "Unpublished"


class Form_Participant(models.Model):
    REGISTRATION_TYPE_CHOICES = [
        ('participant', 'General Participant / Delegate'),
        ('competition', 'Competition'),
    ]
    DEPARTMENT_CHOICES = [
        ('eee', 'Electrical & Electronic Engineering'),
        ('mech_civil', 'Mechanical / Civil Engineering'),
        ('bba_econ', 'Business Administration / Economics'),
        ('env_policy', 'Environmental Science & Policy'),
        ('cs', 'Computer Science'),
        ('other', 'Other'),
    ]
    STUDY_LEVEL_CHOICES = [
        ('undergrad', 'Undergraduate Student'),
        ('grad', "Graduate / Master's Student"),
        ('fresh_grad', 'Fresh Graduate'),
        ('faculty', 'Faculty / Academician'),
        ('industry', 'Industry Professional'),
    ]
    TRACK_CHOICES = [
        ('track_a', 'Track A: Grid Modernization, Smart Grids & Load-Shedding Mitigation'),
        ('track_b', 'Track B: Renewable Integration, Energy Storage & Decarbonization'),
        ('track_c', 'Track C: Energy Policy, FDI Frameworks & Market Restructuring'),
    ]
    MEMBERSHIP_CHOICES = [
        ('ieee', 'IEEE Member'),
        ('non_ieee', 'Non-IEEE Member'),
    ]
    MEMBER_COUNT_CHOICES = [
        ('1', 'Solo (1 Member)'),
        ('2', '2 Members'),
        ('3', '3 Members'),
    ]

    registration_type = models.CharField(max_length=20, choices=REGISTRATION_TYPE_CHOICES)

    # Personal info — both flows
    name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    university = models.CharField(max_length=200)
    department = models.CharField(max_length=20, choices=DEPARTMENT_CHOICES)
    student_id = models.CharField(max_length=50)
    study_level = models.CharField(max_length=20, choices=STUDY_LEVEL_CHOICES)
    ambassador_code = models.CharField(max_length=50, blank=True, null=True, default='')

    # Participant payment
    membership_type = models.CharField(max_length=20, choices=MEMBERSHIP_CHOICES, blank=True, null=True)

    # Competition — team leader extra
    ieee_id = models.CharField(max_length=50, blank=True, null=True, default='')

    # Competition — team
    team_name = models.CharField(max_length=200, blank=True, null=True)
    total_members = models.CharField(max_length=5, choices=MEMBER_COUNT_CHOICES, blank=True, null=True)

    # Member 2
    mem2_name = models.CharField(max_length=200, blank=True, null=True, default='')
    mem2_university = models.CharField(max_length=200, blank=True, null=True, default='')
    mem2_department = models.CharField(max_length=200, blank=True, null=True, default='')
    mem2_student_id = models.CharField(max_length=50, blank=True, null=True, default='')
    mem2_email = models.EmailField(blank=True, null=True, default='')
    mem2_phone = models.CharField(max_length=20, blank=True, null=True, default='')

    # Member 3
    mem3_name = models.CharField(max_length=200, blank=True, null=True, default='')
    mem3_university = models.CharField(max_length=200, blank=True, null=True, default='')
    mem3_department = models.CharField(max_length=200, blank=True, null=True, default='')
    mem3_student_id = models.CharField(max_length=50, blank=True, null=True, default='')
    mem3_email = models.EmailField(blank=True, null=True, default='')
    mem3_phone = models.CharField(max_length=20, blank=True, null=True, default='')

    # Competition — project
    track = models.CharField(max_length=20, choices=TRACK_CHOICES, blank=True, null=True)
    project_title = models.CharField(max_length=300, blank=True, null=True)
    problem_statement = models.TextField(blank=True, null=True)
    proposed_solution = models.TextField(blank=True, null=True)
    sdg_alignment = models.JSONField(default=list, blank=True)
    abstract_file = models.CharField(max_length=255, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Form Participant"

    def __str__(self):
        return f"{self.name} — {self.get_registration_type_display()}"
