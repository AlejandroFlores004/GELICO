#!/bin/sh

# First run: install Tailwind's npm dependencies (node_modules is gitignored)
if [ ! -d theme/static_src/node_modules ]; then
    echo "Primer arranque: instalando dependencias de Tailwind..."
    python manage.py tailwind install || exit 1
fi

# Apply pending migrations, if any
if ! python manage.py migrate --check > /dev/null 2>&1; then
    echo "Hay migraciones pendientes: aplicándolas..."
    python manage.py migrate --noinput || exit 1
fi

# Start Tailwind watcher in the background
python manage.py tailwind start &

# Start Django development server
python manage.py runserver 0.0.0.0:8000
