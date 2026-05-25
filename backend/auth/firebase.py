import firebase_admin
from firebase_admin import credentials, auth
import os
import json
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class FirebaseAuth:
    def __init__(self):
        self.app = None
        self.credentials = None
        self._initialize_firebase()
    
    def _initialize_firebase(self):
        """Inicializar Firebase Admin SDK"""
        try:
            # Verificar si ya hay una app de Firebase inicializada
            if not firebase_admin._apps:
                import json
                cred_json = os.getenv('FIREBASE_CREDENTIALS_JSON')
                cred_path = os.getenv('FIREBASE_CREDENTIALS_PATH')
                
                if cred_json:
                    # En producción (Cloud Run): Lee el JSON directamente desde una variable de entorno secreta
                    cred_dict = json.loads(cred_json)
                    cred = credentials.Certificate(cred_dict)
                    self.app = firebase_admin.initialize_app(cred)
                    logger.info("Firebase Admin SDK inicializado desde JSON en variable de entorno")
                elif cred_path and os.path.exists(cred_path):
                    # En local: Lee el archivo físico si existe
                    cred = credentials.Certificate(cred_path)
                    self.app = firebase_admin.initialize_app(cred)
                    logger.info("Firebase Admin SDK inicializado correctamente desde archivo")
                else:
                    # Si todo falla, intenta usar Credenciales por Defecto de la Aplicación (ADC) de Google Cloud
                    try:
                        self.app = firebase_admin.initialize_app()
                        logger.info("Firebase Admin SDK inicializado con Credenciales por Defecto (ADC)")
                    except Exception as e:
                        logger.warning("No se encontraron credenciales de Firebase válidas (JSON, Path o ADC)")
            else:
                self.app = firebase_admin.get_app()
                logger.info("Firebase Admin SDK ya estaba inicializado")
                
        except Exception as e:
            logger.error(f"Error inicializando Firebase: {e}")
            self.app = None
    
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verificar token de Firebase y obtener información del usuario"""
        try:
            if not self.app:
                logger.error("❌ Firebase no está inicializado")
                return None
                
            # Verificar el token
            decoded_token = auth.verify_id_token(token)
            
            return {
                'uid': decoded_token['uid'],
                'email': decoded_token.get('email'),
                'name': decoded_token.get('name'),
                'picture': decoded_token.get('picture'),
                'email_verified': decoded_token.get('email_verified', False)
            }
            
        except Exception as e:
            logger.error(f"❌ Error verificando token: {e}")
            return None
    
    def get_user(self, uid: str) -> Optional[Dict[str, Any]]:
        """Obtener información de usuario por UID"""
        try:
            if not self.app:
                return None
                
            user = auth.get_user(uid)
            return {
                'uid': user.uid,
                'email': user.email,
                'name': user.display_name,
                'picture': user.photo_url,
                'email_verified': user.email_verified,
                'created_at': user.user_metadata.get('creation_time'),
                'last_sign_in': user.user_metadata.get('last_sign_in_time')
            }
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo usuario: {e}")
            return None
    
    def create_custom_token(self, uid: str, additional_claims: Optional[Dict] = None) -> Optional[str]:
        """Crear token personalizado para el usuario"""
        try:
            if not self.app:
                return None
                
            custom_token = auth.create_custom_token(uid, additional_claims)
            return custom_token.decode('utf-8')
            
        except Exception as e:
            logger.error(f"❌ Error creando token personalizado: {e}")
            return None

# Instancia global
firebase_auth = FirebaseAuth()
