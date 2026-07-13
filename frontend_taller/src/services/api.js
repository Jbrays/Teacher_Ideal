const API_CONFIG = {
  development: { baseURL: 'http://localhost:8000' },
  production: { baseURL: import.meta.env.VITE_API_BASE_URL || 'https://vektora-5ymh5ybzya-uc.a.run.app' }
};

const isDev = location.hostname === 'localhost' || location.hostname === '127.0.0.1';
const API_BASE_URL = isDev ? API_CONFIG.development.baseURL : API_CONFIG.production.baseURL;

export function apiURL(endpoint) {
  const path = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  return `${API_BASE_URL}${path}`;
}

import { auth } from './firebase';

// Helper para obtener el token de Firebase (y Google opcional)
async function getAuthHeaders(googleToken = null) {
  let firebaseToken = localStorage.getItem('firebase_id_token');

  if (auth.currentUser) {
    try {
      firebaseToken = await auth.currentUser.getIdToken();
      localStorage.setItem('firebase_id_token', firebaseToken);
    } catch (e) {
      console.warn("Error refrescando token de Firebase:", e);
    }
  }

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
      headers: await getAuthHeaders()
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
 * Obtener el estado del procesamiento en segundo plano
 */
export async function fetchSystemStatus() {
  try {
    const response = await fetch(apiURL(`/api/system/status`), {
      method: 'GET',
      headers: await getAuthHeaders()
    });

    if (!response.ok) return { is_processing: false, pending_count: 0 };
    return await response.json();
  } catch (error) {
    return { is_processing: false, pending_count: 0 };
  }
}

/**
 * Obtener recomendaciones de docentes para un curso específico
 */
export async function fetchRecommendations(cursoId, topK = 100) {
  try {
    const response = await fetch(apiURL(`/api/recommend/docentes/${cursoId}?top_k=${topK}`), {
      method: 'GET',
      headers: await getAuthHeaders()
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
      headers: await getAuthHeaders(googleToken)
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
 * Configurar Webhooks para todas las carpetas juntas
 */
export async function configAllWebhooks(folders, googleToken) {
  try {
    const payload = {
      cvs_folder_id: folders.cvs?.id,
      syllabi_folder_id: folders.syllabi?.id,
      schedules_folder_id: folders.schedules?.id
    };

    const response = await fetch(apiURL('/api/webhooks/config_all'), {
      method: 'POST',
      headers: {
        ...(await getAuthHeaders(googleToken)),
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(`Error ${response.status}: ${errorData.detail || response.statusText}`);
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Error configurando todos los webhooks:', error);
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
      headers: await getAuthHeaders()
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

/**
 * Limpiar toda la base de datos
 */
export async function clearDatabase() {
  try {
    const response = await fetch(apiURL('/api/admin/clear_db'), {
      method: 'DELETE',
      headers: await getAuthHeaders()
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(`Error ${response.status}: ${errorData.detail || response.statusText}`);
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Error limpiando base de datos:', error);
    throw error;
  }
}

/**
 * Exportar todas las recomendaciones a CSV
 */
export async function exportAllRecommendations() {
  try {
    const response = await fetch(apiURL('/api/admin/export_recommendations'), {
      method: 'GET',
      headers: await getAuthHeaders()
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(`Error ${response.status}: ${errorData.detail || response.statusText}`);
    }

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'recomendaciones_completas.csv';
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);

    return true;
  } catch (error) {
    console.error('Error exportando recomendaciones:', error);
    throw error;
  }
}

/**
 * Exportar las recomendaciones de un curso específico a PDF
 */
export async function exportCursoRecommendationsPdf(cursoId, cursoNombre) {
  try {
    const response = await fetch(apiURL(`/api/recommend/docentes/${cursoId}/export_pdf`), {
      method: 'GET',
      headers: await getAuthHeaders()
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(`Error ${response.status}: ${errorData.detail || response.statusText}`);
    }

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ranking_${(cursoNombre || 'curso').replace(/ /g, '_').substring(0, 30)}.pdf`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);

    return true;
  } catch (error) {
    console.error(`Error exportando PDF del curso ${cursoId}:`, error);
    throw error;
  }
}

/**
 * Obtener todos los colaboradores
 */
export async function fetchColaboradores() {
  try {
    const response = await fetch(apiURL('/api/colaboradores'), {
      method: 'GET',
      headers: await getAuthHeaders()
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(`Error ${response.status}: ${errorData.detail || response.statusText}`);
    }
    const data = await response.json();
    return data.colaboradores || [];
  } catch (error) {
    console.error('Error obteniendo colaboradores:', error);
    throw error;
  }
}

/**
 * Añadir un colaborador
 */
export async function addColaborador(email) {
  try {
    const response = await fetch(apiURL('/api/colaboradores'), {
      method: 'POST',
      headers: await getAuthHeaders(),
      body: JSON.stringify({ invitado_email: email })
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(`Error ${response.status}: ${errorData.detail || response.statusText}`);
    }
    return await response.json();
  } catch (error) {
    console.error('Error añadiendo colaborador:', error);
    throw error;
  }
}

/**
 * Eliminar un colaborador
 */
export async function removeColaborador(email) {
  try {
    const response = await fetch(apiURL(`/api/colaboradores/${encodeURIComponent(email)}`), {
      method: 'DELETE',
      headers: await getAuthHeaders()
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(`Error ${response.status}: ${errorData.detail || response.statusText}`);
    }
    return await response.json();
  } catch (error) {
    console.error(`Error eliminando colaborador ${email}:`, error);
    throw error;
  }
}