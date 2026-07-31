import { configWebhook, configAllWebhooks } from './api';
import {
  auth,
  authorizeDriveOffline,
  refreshAndSyncDriveAccessToken
} from './firebase';

export { configWebhook, configAllWebhooks };

async function ensureFreshGoogleToken() {
  const sessionUid = auth.currentUser?.uid;
  if (!sessionUid) {
    throw new Error('La sesión no está activa. Inicia sesión nuevamente.');
  }

  try {
    const token = await refreshAndSyncDriveAccessToken();
    if (token) return token;
  } catch (e) {
    console.warn('Refresh silencioso de Drive falló; solicitando autorización para la sesión actual:', e);
  }

  await authorizeDriveOffline({ forceConsent: true });
  const token = await refreshAndSyncDriveAccessToken();

  if (!auth.currentUser || auth.currentUser.uid !== sessionUid) {
    throw new Error('La sesión cambió durante la autorización de Drive. Vuelve a iniciar sesión.');
  }
  if (!token) {
    throw new Error('No se pudo renovar el acceso a Drive para la sesión actual.');
  }
  return token;
}

let pickerApiLoaded = false;


/**
 * Inicializar Google Picker API
 */
export async function initDriveAPI() {
  if (pickerApiLoaded || typeof gapi === 'undefined') {
    return pickerApiLoaded;
  }

  return new Promise((resolve) => {
    gapi.load('picker', () => {
      pickerApiLoaded = true;
      console.log('Google Picker API cargada');
      resolve(true);
    });
  });
}

/**
 * Seleccionar una carpeta de Google Drive
 */
export async function selectFolder(type) {
  let accessToken = localStorage.getItem('googleToken');
  const expiresAt = localStorage.getItem('googleToken_expires_at');

  if (!accessToken || !expiresAt || Date.now() > parseInt(expiresAt, 10)) {
    accessToken = await ensureFreshGoogleToken();
  }

  if (!accessToken) {
    alert('Necesitas iniciar sesión con Google para acceder a Drive');
    throw new Error('No access token');
  }

  // Asegurar que el API esté cargado
  if (!pickerApiLoaded) {
    await initDriveAPI();
  }

  const titles = {
    cvs: 'Selecciona la carpeta de CVs',
    syllabi: 'Selecciona la carpeta de Sílabos',
    schedules: 'Selecciona la carpeta de Horarios'
  };

  return new Promise((resolve, reject) => {
    const docsView = new google.picker.DocsView(google.picker.ViewId.FOLDERS)
      .setIncludeFolders(true)
      .setSelectFolderEnabled(true)
      .setOwnedByMe(true);

    const picker = new google.picker.PickerBuilder()
      .addView(docsView)
      .setOAuthToken(accessToken)
      .setCallback((data) => {
        if (data[google.picker.Response.ACTION] === google.picker.Action.PICKED) {
          const folder = data[google.picker.Response.DOCUMENTS][0];
          const folderData = {
            id: folder[google.picker.Document.ID],
            name: folder[google.picker.Document.NAME]
          };
          console.log(`📁 Carpeta seleccionada (${type}):`, folderData.name);
          resolve(folderData);
        } else if (data[google.picker.Response.ACTION] === google.picker.Action.CANCEL) {
          resolve(null);
        }
      })
      .setTitle(titles[type] || 'Selecciona una carpeta')
      .build();

    picker.setVisible(true);
  });
}

/**
 * Sincronizar y vincular todas las carpetas (Webhooks)
 */
export async function processAllData(folders) {
  const results = {
    success: false,
    messages: []
  };

  const sessionUid = auth.currentUser?.uid;
  if (!sessionUid) {
    throw new Error('La sesión no está activa. Inicia sesión nuevamente.');
  }

  // Siempre token fresco antes de encolar (el backend además renueva con refresh_token)
  let googleToken = await ensureFreshGoogleToken();

  if (!auth.currentUser || auth.currentUser.uid !== sessionUid) {
    throw new Error('La sesión cambió antes de iniciar el procesamiento. Vuelve a iniciar sesión.');
  }

  if (!googleToken) {
    alert("No se encontró el token de Google. Por favor, inicie sesión de nuevo.");
    throw new Error("Missing Google Token");
  }

  try {
    if (folders.cvs?.id && folders.syllabi?.id && folders.schedules?.id) {
      console.log('🔗 Vinculando todas las carpetas sincrónicamente...');
      const res = await configAllWebhooks(folders, googleToken);
      results.messages.push(res.message);
    } else {
      // Fallback si no están las 3
      if (folders.cvs?.id) {
        console.log('🔗 Vinculando CVs...');
        const res = await configWebhook(folders.cvs.id, googleToken);
        results.messages.push(`CVs: ${res.message}`);
      }
      if (folders.syllabi?.id) {
        console.log('🔗 Vinculando sílabos...');
        const res = await configWebhook(folders.syllabi.id, googleToken);
        results.messages.push(`Sílabos: ${res.message}`);
      }
      if (folders.schedules?.id) {
        console.log('🔗 Vinculando horarios...');
        const res = await configWebhook(folders.schedules.id, googleToken);
        results.messages.push(`Horarios: ${res.message}`);
      }
    }

    results.success = true;
    return results;

  } catch (error) {
    console.error('❌ Error configurando webhooks:', error);
    results.error = error.message;
    throw error;
  }
}
