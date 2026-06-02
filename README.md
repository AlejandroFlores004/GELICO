# GELICO

**GELICO** significa **Gestión de Liquidaciones y Convocatorias**.

## Descripción

GELICO es un sistema desarrollado para facilitar la gestión y el control de liquidaciones y convocatorias dentro de una organización. Su objetivo es centralizar la información y agilizar los procesos administrativos relacionados con estas actividades.

## Tecnologías utilizadas

* Python 3.13
* Django
* Docker
* Docker Compose
* SQLite (entorno de desarrollo)

## Requisitos

Antes de comenzar, asegúrese de tener instalado:

* Docker
* Docker Compose

## Instalación del proyecto

### 1. Clonar el repositorio

```bash
git clone https://github.com/AlejandroFlores004/GELICO.git
cd GELICO
```

### 2. Construir la imagen Docker

```bash
docker compose build
```

### 3. Ejecutar las migraciones

```bash
docker compose run --rm web python manage.py migrate
```

### 4. Iniciar el proyecto

```bash
docker compose up
```

O bien, para ejecutarlo en segundo plano:

```bash
docker compose up -d
```

### 5. Acceder al sistema

Una vez iniciado el contenedor, el sistema estará disponible en:

```text
http://localhost:8000
```

## Comandos útiles

### Crear una nueva aplicación Django

```bash
docker compose run --rm web python manage.py startapp nombre_app
```

### Crear un superusuario

```bash
docker compose run --rm web python manage.py createsuperuser
```

### Ejecutar migraciones

```bash
docker compose run --rm web python manage.py migrate
```

### Crear migraciones

```bash
docker compose run --rm web python manage.py makemigrations
```

### Detener los contenedores

```bash
docker compose down
```

## Estructura del proyecto

```text
GELICO/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── manage.py
├── README.md
├── .gitignore
└── gelico/
```

## Autor

Desarrollado por Alejandro Flores.
