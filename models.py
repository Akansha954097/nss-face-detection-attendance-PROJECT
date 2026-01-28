from django.db import models
from django.contrib.auth.models import User
#from django.core.mail import send_mail
from django.conf import settings
import os
from django.db.models.signals import post_save
from django.dispatch import receiver


class Student(models.Model):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('coordinator', 'Coordinator'),
        ('student', 'Student'),
    ]

    APPROVAL_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    student_id = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=15)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')
    photo = models.ImageField(upload_to='student_photos/')
    approval_status = models.CharField(max_length=20, choices=APPROVAL_CHOICES, default='pending')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.student_id})"

    def delete(self, *args, **kwargs):
        """Delete photo file when student is deleted."""
        if self.photo and os.path.isfile(self.photo.path):
            os.remove(self.photo.path)
        super().delete(*args, **kwargs)


class Event(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField()
    date = models.DateField()
    time = models.TimeField()
    venue = models.CharField(max_length=200)
    coordinator = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'coordinator'}
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title



class Attendance(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    attendance_time = models.DateTimeField(auto_now_add=True)
    marked_by = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='marked_attendances'
    )
    is_manual = models.BooleanField(default=False)  # For manually marked attendance
    notes = models.TextField(blank=True, null=True)  # For manual attendance notes

    class Meta:
        unique_together = ['student', 'event']

    def __str__(self):
        return f"{self.student.name} - {self.event.title}"



class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    url = models.CharField(max_length=300, blank=True)
    approve_url = models.CharField(max_length=300, blank=True)
    reject_url = models.CharField(max_length=300, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username}: {self.title}"



#SIGNALS
# Auto-create a Student when a User is created (default student role)
@receiver(post_save, sender=User)
def create_student_profile(sender, instance, created, **kwargs):
    if created:
        Student.objects.create(
            user=instance,
            student_id=getattr(instance, 'temp_student_id', f"STU{instance.id:04d}"),
            name=instance.get_full_name() or instance.username,
            email=instance.email
        )


# Send welcome email when a new student is created
'''@receiver(post_save, sender=Student)
def send_student_creation_email(sender, instance, created, **kwargs):
    if created:
        try:
            subject = "Welcome to NSS Face Attendance System"
            message = f"""
Hello {instance.name},

Your NSS account has been created successfully!

Account Details:
- Student ID: {instance.student_id}
- Role: {instance.get_role_display()}
- Username: {instance.user.username}

Please login to the system and update your profile.

Best regards,
NSS Team
"""
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [instance.email],
                fail_silently=False,
            )
        except Exception as e:
            print(f"Welcome email failed: {e}")


# Send email when an event’s status changes
@receiver(post_save, sender=Event)
def send_event_status_email(sender, instance, created, **kwargs):
    if not created:  # Only for updates
        try:
            old_instance = Event.objects.get(pk=instance.pk)
            if old_instance.status != instance.status:
                subject = f"Event Status Update: {instance.title}"
                message = f"""
Hello {instance.coordinator.name},

Your event "{instance.title}" has been {instance.status} by admin.

Event Details:
- Date: {instance.date}
- Time: {instance.time}
- Venue: {instance.venue}

Thank you for your contribution!

Best regards,
NSS Team
"""
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [instance.coordinator.email],
                    fail_silently=False,
                )
        except Event.DoesNotExist:
            pass
        except Exception as e:
            print(f"Event status email failed: {e}")'''
