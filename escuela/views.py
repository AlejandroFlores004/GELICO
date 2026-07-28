from django.shortcuts import render

# Create your views here.
def encargadoHomeView(request):
    return render(request, 'encargado/encargadoHome.html')