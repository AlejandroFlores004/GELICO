from django.shortcuts import render
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required

# Create your views here.
@login_required(login_url='login')
def home_view(request):
    return render(request, 'home.html')

def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")  # change to your home url name

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect("home")  # change to your home url name
        else:
            messages.error(request, "Invalid username or password.")

    return render(request, "registration/login.html")


def logout_view(request):
    logout(request)
    return redirect("login")