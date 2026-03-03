#!/bin/bash

TARGET_DIR="./"   # Cambia si tu código está en otra carpeta

echo "🔍 Buscando y reemplazando 'use_container_width' en $TARGET_DIR ..."

# Reemplazar width="stretch" → width="stretch"
grep -rl "width="stretch"" "$TARGET_DIR" | while read -r file; do
    sed -i 's/width="stretch"/width="stretch"/g' "$file"
    echo "✔️  Actualizado: $file"
done

# Reemplazar width="content" → width="content"
grep -rl "width="content"" "$TARGET_DIR" | while read -r file; do
    sed -i 's/width="content"/width="content"/g' "$file"
    echo "✔️  Actualizado: $file"
done

echo "🎉 Reemplazo completado."
