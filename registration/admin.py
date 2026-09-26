from django.contrib import admin

from .models import *
# Register your models here.

@admin.register(EventFormStatus)
class EventFormStatusAdmin(admin.ModelAdmin):
    list_display = ['is_published', 'updated_at']

@admin.register(Form_Participant)
class Form_ParticipantAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'registration_type', 'university', 'email', 'created_at']