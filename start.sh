#!/bin/sh

# Start Tailwind watcher in the background
python manage.py tailwind start &

# Start Django development server
python manage.py runserver 0.0.0.0:8000