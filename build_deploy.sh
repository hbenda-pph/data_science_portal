#!/bin/bash

# =============================================================================
# SCRIPT DE BUILD & DEPLOY PARA DATA SCIENCE INDEX (FLASK)
# Multi-Environment: DEV, QUA, PRO
# =============================================================================

set -e  # Salir si hay algún error

# =============================================================================
# CONFIGURACIÓN DE AMBIENTES
# =============================================================================

# Detectar proyecto activo de gcloud
CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null)

# Si se proporciona parámetro, usarlo; si no, detectar automáticamente
if [ -n "$1" ]; then
    # Parámetro proporcionado explícitamente
    ENVIRONMENT="$1"
    ENVIRONMENT=$(echo "$ENVIRONMENT" | tr '[:upper:]' '[:lower:]')  # Convertir a minúsculas
    
    # Validar ambiente
    if [[ ! "$ENVIRONMENT" =~ ^(dev|qua|pro)$ ]]; then
        echo "❌ Error: Ambiente inválido '$ENVIRONMENT'"
        echo "Uso: ./build_deploy.sh [dev|qua|pro]"
        exit 1
    fi
else
    # Detectar automáticamente según el proyecto activo
    case "$CURRENT_PROJECT" in
        *-des) ENVIRONMENT="dev" ;;
        *-qua) ENVIRONMENT="qua" ;;
        *-pro) ENVIRONMENT="pro" ;;
        *)
            echo "❌ Error: No se pudo determinar el ambiente a partir del proyecto activo: $CURRENT_PROJECT"
            echo "Uso: ./build_deploy.sh [dev|qua|pro] o asegúrate de tener un proyecto activo con el sufijo -des, -qua, o -pro."
            exit 1
            ;;
    esac
fi

# =============================================================================
# ASIGNACIÓN DE VARIABLES
# =============================================================================

# Define los IDs de proyecto según el ambiente. ¡Asegúrate de que sean tus IDs reales!
case "$ENVIRONMENT" in
    dev)
        PROJECT_ID="platform-partners-des" 
        SERVICE_NAME="ds-inflection-portal-dev"
        REGION="us-central1" # Ajusta tu región de DEV
        ;;
    qua)
        PROJECT_ID="platform-partners-qua" 
        SERVICE_NAME="ds-inflection-portal-qua"
        REGION="us-central1" # Ajusta tu región de QUA
        ;;
    pro)
        PROJECT_ID="platform-partners-pro" 
        SERVICE_NAME="ds-inflection-portal-pro"
        REGION="us-central1" # Ajusta tu región de PRO
        ;;
esac

TAG="gcr.io/${PROJECT_ID}/${SERVICE_NAME}:${ENVIRONMENT}"

echo ""
echo "=========================================="
echo "🚀 INICIANDO BUILD & DEPLOY - ${ENVIRONMENT^^} ENVIRONMENT"
echo "=========================================="
echo "Proyecto (ID): ${PROJECT_ID}"
echo "Servicio:      ${SERVICE_NAME}"
echo "Región:        ${REGION}"
echo "TAG:           ${TAG}"
echo "=========================================="
echo ""

# 1. BUILD DEL CONTENEDOR (Cloud Build)
echo "📦 1. Building container image..."
gcloud builds submit --tag "${TAG}" --project "${PROJECT_ID}"

# 2. DEPLOY A CLOUD RUN
echo "☁️ 2. Deploying service to Cloud Run..."
# Utilizamos la sintaxis de Bash con \ al final de la línea para evitar el error 'command not found'
# Se utiliza '--allow-unauthenticated' para que sea accesible públicamente (ajusta si necesitas IAM)
gcloud run deploy "${SERVICE_NAME}" \
    --image "${TAG}" \
    --region "${REGION}" \
    --platform "managed" \
    --allow-unauthenticated \
    --project "${PROJECT_ID}" \
    --cpu "1" \
    --memory "512Mi" \
    --min-instances "0" \
    --max-instances "5" \
    --port "8080" \
    --quiet

# =============================================================================
# FINALIZACIÓN
# =============================================================================
echo ""
echo "=================================="
echo "✅ DEPLOYADO EXITOSAMENTE!"
echo "=================================="
echo ""
echo "🌍 AMBIENTE: ${ENVIRONMENT^^}"
echo "📊 Información del servicio:"
echo "   Proyecto: ${PROJECT_ID}"
echo "   Servicio: ${SERVICE_NAME}"
echo "   Región:   ${REGION}"
echo ""
echo "🌐 Para ver tu aplicación:"
gcloud run services describe ${SERVICE_NAME} --region=${REGION} --project=${PROJECT_ID} --format='value(status.url)'
echo ""
echo "🔧 Para ver logs en tiempo real:"
echo "   gcloud run services logs read ${SERVICE_NAME} --region=${REGION} --project=${PROJECT_ID} --tail"
echo ""
echo "🔄 Para deploy en otros ambientes:"
echo "   ./build_deploy.sh qua    # Deploy en QUA (validación y QA)"
echo "   ./build_deploy.sh pro    # Deploy en PRO (producción)"
echo ""