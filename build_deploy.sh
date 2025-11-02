#!/bin/bash

#=============================================================================
#SCRIPT DE BUILD & DEPLOY PARA PORTAL DE DATOS (FLASK/CLOUD RUN)
#Multi-Environment: DEV, QUA, PRO
#=============================================================================

set -e  # Salir si hay algún error

#=============================================================================
#CONFIGURACIÓN DE AMBIENTES
#=============================================================================

#Detectar proyecto activo de gcloud

CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null)

#Verificar si se proporcionó un ambiente como parámetro

if [ -n "$1" ]; then
ENVIRONMENT="$1"
ENVIRONMENT=$(echo "$ENVIRONMENT" | tr '[:upper:]' '[:lower:]')  # Convertir a minúsculas
else
# Si no se proporciona ambiente, se deduce del proyecto activo (lógica heredada)
if [[ "$CURRENT_PROJECT" == "dev" || "$CURRENT_PROJECT" == "des" ]]; then
ENVIRONMENT="dev"
elif [[ "$CURRENT_PROJECT" == "qua" ]]; then
ENVIRONMENT="qua"
elif [[ "$CURRENT_PROJECT" == "pro" ]]; then
ENVIRONMENT="pro"
else
echo "⚠️ Advertencia: No se detectó ambiente (dev/qua/pro) en el nombre del proyecto activo."
echo "Asumiendo 'dev' por defecto."
ENVIRONMENT="dev"
fi
fi

#Asignar nombres y IDs de proyecto basados en el ambiente

case "$ENVIRONMENT" in
dev)
PROJECT_ID="platform-partners-des" # ID de tu proyecto DEV
SERVICE_NAME="ds-inflection-portal-dev"
REGION="us-central1"
;;
qua)
PROJECT_ID="platform-partners-qua" # ID de tu proyecto QUA
SERVICE_NAME="ds-inflection-portal-qua"
REGION="us-central1"
;;
pro)
PROJECT_ID="platform-partners-pro" # ID de tu proyecto PRO
SERVICE_NAME="ds-inflection-portal-pro"
REGION="us-central1"
;;
*)
echo "❌ Error: Ambiente inválido '$ENVIRONMENT'"
echo "Uso: ./build_deploy.sh [dev|qua|pro]"
exit 1
;;
esac

#=============================================================================
#PASO 1: CONFIGURAR PROYECTO Y GCR
#=============================================================================

echo "🛠️ Configurando GCloud para el ambiente $ENVIRONMENT..."
gcloud config set project "$PROJECT_ID"

ID de la imagen en Google Container Registry (GCR) o Artifact Registry

IMAGE_TAG="gcr.io/${PROJECT_ID}/${SERVICE_NAME}:${ENVIRONMENT}_$(date +%Y%m%d%H%M%S)"

#=============================================================================
#PASO 2: CONSTRUIR LA IMAGEN DOCKER (BUILD)
#=============================================================================

echo ""
echo "📦 Iniciando build de la imagen Docker para $ENVIRONMENT..."
echo "   TAG: $IMAGE_TAG"
echo "   Proyecto: $PROJECT_ID"
echo "   Servicio: $SERVICE_NAME"

Se usa el Dockerfile en el directorio actual

gcloud builds submit --tag "$IMAGE_TAG" . --timeout="30m"

#=============================================================================
#PASO 3: DESPLEGAR EN CLOUD RUN (DEPLOY)
#=============================================================================

echo ""
echo "🚀 Desplegando imagen en Cloud Run..."
gcloud run deploy "$SERVICE_NAME" \
--image "${IMAGE_TAG}" \
--region "${REGION}" \
--platform "managed" \
--allow-unauthenticated 
--port 8080 \
--memory 1Gi \
--cpu 1 \
--timeout 3600 \
--project "${PROJECT_ID}" 
--quiet    

#NOTA: Se usa --allow-unauthenticated para un portal público. Si se requiere autenticación,
#cambiar a --no-allow-unauthenticated y configurar IAM.

#=============================================================================
#PASO 4: RESULTADOS
#=============================================================================

echo ""
echo "=================================="
echo "✅ DEPLOY COMPLETADO EXITOSAMENTE!"
echo "=================================="
echo ""
echo "🌍 AMBIENTE: ${ENVIRONMENT^^}"
echo "📊 Información del servicio:"
echo "   Proyecto: ${PROJECT_ID}"
echo "   Servicio: ${SERVICE_NAME}"
echo "   Región:   ${REGION}"
echo ""
echo "🌐 Para ver tu aplicación (puede tardar unos segundos en ser accesible):"
gcloud run services describe "${SERVICE_NAME}" --region="${REGION}" --project="${PROJECT_ID}" --format='value(status.url)'
echo ""
echo "🔧 Para ver logs en tiempo real:"
echo "   gcloud run services logs read ${SERVICE_NAME} --region=${REGION} --project=${PROJECT_ID} --tail"
echo ""
echo "🔄 Para deploy en otros ambientes:"
echo "   ./build_deploy.sh dev    # Deploy en DEV"
echo "   ./build_deploy.sh qua    # Deploy en QUA"
echo "   ./build_deploy.sh pro    # Deploy en PRO"
echo ""