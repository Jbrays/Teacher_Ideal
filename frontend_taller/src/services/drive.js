import { processCVs, processSyllabi, processSchedules } from './api';

export { processCVs, processSyllabi, processSchedules };

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
  // Esta función usa el 'googleToken' para el Picker
  const accessToken = localStorage.getItem('googleToken');

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
 * Procesar todos los archivos de las carpetas seleccionadas
 */
export async function processAllData(folders) {
  const results = {
    docentes: [],
    ciclos: [],
    cursos: {},
    historial: null,
    success: false
  };

  // Obtener el token de Google para pasarlo al backend (necesario para descargar archivos)
  const googleToken = localStorage.getItem('googleToken');
  if (!googleToken) {
    alert("No se encontró el token de Google. Por favor, inicie sesión de nuevo.");
    throw new Error("Missing Google Token");
  }

  try {
    // 1. Procesar CVs
    if (folders.cvs?.id) {
      console.log('📄 Procesando CVs...');
      const cvsData = await processCVs(folders.cvs.id, googleToken);
      results.docentes = cvsData.docentes || [];
      console.log(`✅ ${cvsData.processed || 0} CVs procesados`);
    }

    // 2. Procesar Sílabos
    if (folders.syllabi?.id) {
      console.log('📘 Procesando sílabos...');
      const syllabiData = await processSyllabi(folders.syllabi.id, googleToken);
      results.ciclos = syllabiData.ciclos || [];
      results.cursos = syllabiData.cursos_por_ciclo || {};
      console.log(`✅ ${syllabiData.processed || 0} sílabos procesados`);
      console.log(`📊 Ciclos encontrados:`, results.ciclos);
    }

    // 3. Procesar Horarios (AHORA HABILITADO)
    if (folders.schedules?.id) {
      console.log('📅 Procesando horarios...');
      const schedulesData = await processSchedules(folders.schedules.id, googleToken);
      results.historial = schedulesData;
      console.log(`✅ Historial actualizado: ${schedulesData.total_history_records_created || 0} registros nuevos`);

      if (schedulesData.errors && schedulesData.errors.length > 0) {
        console.warn(`⚠️ Hubo ${schedulesData.errors.length} errores procesando horarios.`);
      }
    }

    results.success = true;
    return results;

  } catch (error) {
    console.error('❌ Error procesando datos:', error);
    results.error = error.message;
    throw error;
  }
}