from django.db import models
from django.contrib.auth.models import User

# Create your models here.
class Registered_Participant(models.Model):
    '''This model contains data of all the registered participants for the event\n
        It also contains the unique code for the participant. It is set to unique in database to prevent having same code for two participants'''
    
    name=models.CharField(null=False, blank=False, max_length=150)
    university=models.CharField(null=True, blank=True, max_length=150)
    contact_no=models.CharField(null=True, blank=True, max_length=50)
    email=models.EmailField(null=True, blank=True)
    role=models.CharField(null=True, blank=True, max_length=100)
    t_shirt_size=models.CharField(null=True, blank=True, max_length=20)
    unique_code=models.CharField(null=False, blank=False, max_length=150, unique=True)

    class Meta:
        verbose_name="Registered Participant"

    def __str__(self):
        return str(self.pk)

class Token_Session(models.Model):
    '''This model contatins the token session data\n
        `session_name` is the name of the session\n
        -`is_active` when True, sets the session to active. This setting ensures that volunteers only see and are able to scan for active sessions only\n
        -`order_of_session` sets the order in which the sessions will be displayed on screen'''
    
    session_name=models.CharField(null=False, blank=False, max_length=20)
    is_active=models.BooleanField(null=False, blank=False, default=False)
    # is_independent=models.BooleanField(null=False, blank=False, default=False)
    order_of_session=models.IntegerField(null=False,blank=False,default=0)

    class Meta:
        verbose_name="Token Session"

    # def current_session():
    #     return Token_Session.objects.filter(is_active=True, is_independent=False)[0]

    # def save(self, *args, **kwargs):
    #     if (self.pk):
    #         if(kwargs.get('is_active') == 'on' and (kwargs.get('is_independent') == 'off' or self.is_independent == False)):
    #             Token_Session.objects.filter(is_active=True, is_independent=False).update(is_active=False)
        
    #     super().save(*args, **kwargs)

    def __str__(self):
        return str(self.pk)

class Token_Participant(models.Model):
    '''This model stores the relation between token_session and registered_participant.\n
        When a participant qr is scanned for a session, then it is recorded in this model.\n
        -`registered_participant` the participant who qr has been scanned\n
        -`token_session` the session for which the qr has been scanned\n
        -`date_time` the timestamp for when the qr is scanned. (Added automatically)'''
    
    registered_participant=models.ForeignKey(Registered_Participant, null=False, blank=False, on_delete=models.CASCADE)
    token_session=models.ForeignKey(Token_Session, null=False, blank=False, on_delete=models.CASCADE)
    date_time=models.DateTimeField(null=False, blank=False, auto_now_add=True)

    class Meta:
        verbose_name="Applied Participant Token"

    def __str__(self) -> str:
        return str(self.pk)


# class User_Permission(models.Model):
#     '''This model stores the permission data for a site user account.\n
#         -`user` the user for whom the permissions are being set\n
#         -`update_session` when True, lets the user to set any session as active or inactive\n
#         -`scan` when True, lets the user to scan qr codes\n
#         -`scan_any_session` when True, lets the user to scan qr code for all session whether it is active or inactive'''
    
#     user = models.ForeignKey(User, blank=False, null=False, on_delete=models.CASCADE)
#     update_session = models.BooleanField(null=False, blank=False, default=False)
#     scan = models.BooleanField(null=False, blank=False, default=False)
#     scan_any_session = models.BooleanField(null=False, blank=False, default=False)
    
#     class Meta:
#         verbose_name="User Permissions"

#     def __self__(self) -> str:
#         return str(self.pk)