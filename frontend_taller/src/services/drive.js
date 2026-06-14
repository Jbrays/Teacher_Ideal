import { configWebhook, configAllWebhooks } from './api';
import { loginWithGoogle } from './firebase';

export { configWebhook, configAllWebhooks };

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
  // Refrescar el token de Google si expiró (1 hora)
  let accessToken = localStorage.getItem('googleToken');
  const expiresAt = localStorage.getItem('googleToken_expires_at');

  if (!accessToken || !expiresAt || Date.now() > parseInt(expiresAt)) {
    try {
      const res = await loginWithGoogle();
      if (res && res.googleToken) {
        accessToken = res.googleToken;
        localStorage.setItem('googleToken', accessToken);
        localStorage.setItem('googleToken_expires_at', Date.now() + 55 * 60 * 1000);
      }
    } catch (e) {
      console.warn("No se pudo refrescar el token de Google, intentando con el guardado", e);
    }
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

  // Refrescar el token de Google si expiró (1 hora)
  let googleToken = localStorage.getItem('googleToken');
  const expiresAt = localStorage.getItem('googleToken_expires_at');

  if (!googleToken || !expiresAt || Date.now() > parseInt(expiresAt)) {
    try {
      const res = await loginWithGoogle();
      if (res && res.googleToken) {
        googleToken = res.googleToken;
        localStorage.setItem('googleToken', googleToken);
        localStorage.setItem('googleToken_expires_at', Date.now() + 55 * 60 * 1000);
      }
    } catch (e) {
      console.warn("No se pudo refrescar el token de Google, intentando con el guardado", e);
    }
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