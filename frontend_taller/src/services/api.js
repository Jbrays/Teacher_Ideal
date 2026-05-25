const API_CONFIG = {
  development: { baseURL: 'http://localhost:8000' },
  production: { baseURL: 'https://teacher-ideal-121734839794.us-central1.run.app' }
};

const isDev = location.hostname === 'localhost' || location.hostname === '127.0.0.1';
const API_BASE_URL = isDev ? API_CONFIG.development.baseURL : API_CONFIG.production.baseURL;

export function apiURL(endpoint) {
  const path = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  return `${API_BASE_URL}${path}`;
}

// Helper para obtener el token de Firebase (y Google opcional)
function getAuthHeaders(googleToken = null) {
  const firebaseToken = localStorage.getItem('firebase_id_token');

  const headers = {
    'Authorization': `Bearer ${firebaseToken}`,
    'Content-Type': 'application/json'
  };

  if (googleToken) {
    headers['X-Drive-Token'] = googleToken;
  }

  return headers;
}

// ==================== API METHODS ====================

/**
 * Obtener todos los cursos desde el backend
 */
export async function fetchCursos() {
  try {
    const response = await fetch(apiURL('/api/cursos'), {
      method: 'GET',
      headers: getAuthHeaders()
    });

    if (!response.ok) {
      throw new Error(`Error ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Error fetching cursos:', error);
    throw error;
  }
}

/**
 * Obtener recomendaciones de docentes para un curso específico
 */
export async function fetchRecommendations(cursoId, topK = 100) {
  try {
    const response = await fetch(apiURL(`/api/recommend/docentes/${cursoId}?top_k=${topK}`), {
      method: 'GET',
      headers: getAuthHeaders()
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(`Error ${response.status}: ${errorData.detail || response.statusText}`);
    }

    const result = await response.json();

    if (!result.success) {
      throw new Error('La API reportó un error al obtener recomendaciones.');
    }

    return result;
  } catch (error) {
    console.error('Error fetching recommendations:', error);
    throw error;
  }
}

/**
 * Configurar Webhook para una carpeta de Drive
 */
export async function configWebhook(folderId, googleToken) {
  try {
    const response = await fetch(apiURL(`/api/webhooks/config/${folderId}`), {
      method: 'POST',
      headers: getAuthHeaders(googleToken)
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(`Error ${response.status}: ${errorData.detail || response.statusText}`);
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Error configurando webhook:', error);
    throw error;
  }
}

/**
 * Eliminar un docente permanentemente (Derecho al olvido)
 */
export async function deleteDocente(docenteId) {
  try {
    const response = await fetch(apiURL(`/api/docentes/${docenteId}`), {
      method: 'DELETE',
      headers: getAuthHeaders()
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(`Error ${response.status}: ${errorData.detail || response.statusText}`);
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.error(`Error eliminando docente ${docenteId}:`, error);
    throw error;
  }
}