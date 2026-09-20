from django.shortcuts import render


def home_asignaciones(request):
    return render(request, "asignacion/asignacionHome.html")


def home_recibos(request):
    return render(request, "recibo/reciboHome.html")


def home_abonos(request):
    return render(request, "abono/abonoHome.html")


def home_carga_excel(request):
    return render(request, "carga_excel/cargaExcelHome.html")
