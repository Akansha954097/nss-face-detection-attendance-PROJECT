from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Student, Event

class UserRegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)
    student_id = forms.CharField(max_length=20, required=True, label="Student ID")
    name = forms.CharField(max_length=100, required=True)
    phone = forms.CharField(max_length=15, required=True)
    role = forms.ChoiceField(choices=Student.ROLE_CHOICES, initial='student')
    photo = forms.ImageField(required=True)

    class Meta:
        model = User
        fields = ['username', 'student_id', 'name', 'email', 'phone', 'role', 'photo', 'password1', 'password2']

    def clean_student_id(self):
        sid = self.cleaned_data['student_id']
        if Student.objects.filter(student_id=sid).exists():
            raise forms.ValidationError('This Student ID is already registered.')
        return sid

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        # Provide temp_student_id BEFORE saving so the signal can use it
        user.temp_student_id = self.cleaned_data['student_id']
        if commit:
            user.save()
        return user

class StudentForm(forms.ModelForm):
    username = forms.CharField(max_length=150, required=True)
    password = forms.CharField(widget=forms.PasswordInput(), required=True)
    email = forms.EmailField(required=True)

    class Meta:
        model = Student
        fields = [
            'student_id',
            'name',
            'phone',
            'role',
            'photo',
            'is_active',
        ]

    def save(self, commit=True):
        username = self.cleaned_data['username']
        password = self.cleaned_data['password']
        email = self.cleaned_data['email']

        # Create User first so post_save signal can create linked Student
        user = User(username=username, email=email)
        user.set_password(password)
        # Provide temp_student_id for the User->Student signal to use
        user.temp_student_id = self.cleaned_data.get('student_id')
        user.save()

        # Get the Student created by the signal (or create if missing)
        student, _ = Student.objects.get_or_create(user=user)

        # Populate Student fields from form
        student.student_id = self.cleaned_data['student_id']
        student.name = self.cleaned_data['name']
        student.phone = self.cleaned_data['phone']
        student.role = self.cleaned_data['role']
        student.photo = self.cleaned_data['photo']
        student.is_active = self.cleaned_data['is_active']
        student.email = email

        if commit:
            student.save()

        return student
    
class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ['title', 'description', 'date', 'time', 'venue']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'venue': forms.TextInput(attrs={'class': 'form-control'}),
        }

class EventStatusForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ['status']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-control'}),
        }