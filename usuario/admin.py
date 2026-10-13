from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm

from .forms import validar_correo

User = get_user_model()


class CorreoObligatorioMixin:
    """En el admin de Django el correo también es obligatorio y único (por defecto no lo es)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'email' in self.fields:
            self.fields['email'].required = True

    def clean_email(self):
        return validar_correo(self.cleaned_data.get('email'), self.instance.pk)


class CrearUsuarioAdminForm(CorreoObligatorioMixin, AdminUserCreationForm):
    class Meta(AdminUserCreationForm.Meta):
        fields = ('username', 'email')


class EditarUsuarioAdminForm(CorreoObligatorioMixin, UserChangeForm):
    pass


admin.site.unregister(User)


@admin.register(User)
class UsuarioAdmin(UserAdmin):
    form = EditarUsuarioAdminForm
    add_form = CrearUsuarioAdminForm
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'usable_password', 'password1', 'password2'),
        }),
    )
