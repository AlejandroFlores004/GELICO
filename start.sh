#!/bin/sh

# First run: install Tailwind's npm dependencies (node_modules is gitignored)
if [ ! -d theme/static_src/node_modules ]; then
    echo "Primer arranque: instalando dependencias de Tailwind..."
    python manage.py tailwind install || exit 1
fi

# Start Tailwind watcher in the background
python manage.py tailwind start &

# Start Django development server
python manage.py runserver 0.0.0.0:8000
