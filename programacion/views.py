from django.shortcuts import render

# Create your views here.
def auxiliarHomeView(request):
    return render(request,'auxiliar/auxiliarHome.html')