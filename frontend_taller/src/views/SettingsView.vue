<template>
  <div class="bg-background text-on-background min-h-screen flex flex-col font-sans antialiased">
    <!-- Main Content Area -->
    <main class="flex-1 overflow-y-auto w-full px-margin-mobile md:px-margin-desktop py-8">
      
      <!-- Header -->
      <header class="mb-12 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h1 class="font-headline-lg-mobile md:font-headline-lg text-headline-lg-mobile md:text-headline-lg text-on-surface mb-2">Configuración</h1>
          <p class="font-body-lg text-body-lg text-on-surface-variant">Gestiona tu cuenta y la sincronización de repositorios de Google Drive.</p>
        </div>
        <button @click="goBack" class="flex items-center gap-2 px-6 py-2.5 rounded-full bg-surface-variant text-on-surface-variant hover:bg-surface-container-high transition-colors font-label-lg text-label-lg font-medium shadow-sm">
          <span class="material-symbols-outlined text-[20px]">arrow_back</span>
          Volver
        </button>
      </header>

      <div class="grid grid-cols-1 lg:grid-cols-12 gap-gutter-desktop">
        
        <!-- Left Column: User Profile & Danger Zone -->
        <div class="lg:col-span-4 flex flex-col gap-gutter-desktop">
          
          <!-- Profile Card -->
          <section class="bg-surface rounded-card p-6 shadow-[0_2px_8px_rgba(0,0,0,0.05)] border border-surface-variant">
            <h2 class="font-title-lg text-title-lg text-on-surface mb-6 flex items-center gap-2">
              <span class="material-symbols-outlined text-primary">person</span>
              Usuario
            </h2>
            <div class="flex items-center gap-4 mb-8">
              <div class="w-16 h-16 rounded-full bg-primary-container text-on-primary-container flex items-center justify-center font-title-lg text-title-lg shadow-sm">
                AD
              </div>
              <div>
                <p class="font-body-md text-body-md text-on-surface-variant break-all">{{ userEmail }}</p>
              </div>
            </div>
            <button @click="logout" class="w-full py-3 rounded-full border border-outline text-on-surface font-label-lg text-label-lg flex justify-center items-center gap-2 hover:bg-surface-container-low transition-colors">
              <span class="material-symbols-outlined text-[20px]">logout</span>
              Cerrar Sesión
            </button>
          </section>

          <!-- Colaboradores Card -->
          <section class="bg-surface rounded-card p-6 shadow-[0_2px_8px_rgba(0,0,0,0.05)] border border-surface-variant mt-4">
            <h2 class="font-title-lg text-title-lg text-on-surface mb-4 flex items-center gap-2">
              <span class="material-symbols-outlined text-primary">group</span>
              Colaboradores
            </h2>
            <p class="font-body-md text-body-md text-on-surface-variant mb-4">
              Invita a otros correos para que tengan acceso a la configuración y procesamiento de datos.
            </p>
            
            <form @submit.prevent="handleAddColaborador" class="flex flex-col gap-3 mb-6">
              <input 
                v-model="nuevoColaborador" 
                type="email" 
                placeholder="correo@upao.edu.pe" 
                required
                class="w-full px-4 py-3 rounded-lg border border-outline bg-surface-container-lowest text-on-surface focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-colors"
              />
              <button 
                type="submit" 
                :disabled="agregandoColaborador"
                class="w-full py-2.5 rounded-lg bg-secondary-container text-on-secondary-container font-label-lg font-medium hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center justify-center gap-2"
              >
                <span v-if="agregandoColaborador" class="material-symbols-outlined text-[18px] animate-spin">refresh</span>
                <span v-else class="material-symbols-outlined text-[18px]">person_add</span>
                Añadir Colaborador
              </button>
            </form>

            <div class="space-y-3 max-h-48 overflow-y-auto pr-2">
              <div v-if="cargandoColaboradores" class="flex justify-center p-4">
                <span class="material-symbols-outlined animate-spin text-primary">sync</span>
              </div>
              <div v-else-if="colaboradores.length === 0" class="text-center p-4 text-on-surface-variant font-body-sm">
                No hay colaboradores añadidos.
              </div>
              <div 
                v-else
                v-for="col in colaboradores" 
                :key="col.invitado_email"
                class="flex items-center justify-between p-3 rounded-lg bg-surface-container-lowest border border-outline-variant"
              >
                <span class="font-body-md text-on-surface truncate pr-2" :title="col.invitado_email">
                  {{ col.invitado_email }}
                </span>
                <button 
                  @click="handleRemoveColaborador(col.invitado_email)" 
                  class="text-error hover:bg-error-container p-2 rounded-full transition-colors flex-shrink-0 flex items-center justify-center"
                  title="Eliminar colaborador"
                >
                  <span class="material-symbols-outlined text-[18px]">delete</span>
                </button>
              </div>
            </div>
            <p v-if="colaboradorError" class="text-error text-sm mt-3">{{ colaboradorError }}</p>
          </section>

          <!-- Herramientas Dev Card -->
          <section class="bg-surface rounded-card p-6 shadow-[0_2px_8px_rgba(0,0,0,0.05)] border border-primary-container mt-4">
            <h2 class="font-title-lg text-title-lg text-primary mb-4 flex items-center gap-2">
              <span class="material-symbols-outlined">developer_mode</span>
              Herramientas Dev
            </h2>
            <p class="font-body-md text-body-md text-on-surface-variant mb-6">
              Genera los matches faltantes y descarga todas las recomendaciones en CSV. Esto puede tardar varios minutos.
            </p>
            <button @click="handleExportRecommendations" :disabled="exportingRecommendations" class="w-full py-3 rounded-full bg-primary-container text-on-primary-container font-label-lg text-label-lg flex justify-center items-center gap-2 hover:bg-primary/20 transition-colors shadow-sm disabled:opacity-50">
              <span v-if="exportingRecommendations" class="material-symbols-outlined text-[20px] animate-spin">refresh</span>
              <span v-else class="material-symbols-outlined text-[20px]">download</span>
              {{ exportingRecommendations ? 'Exportando...' : 'Exportar Recomendaciones' }}
            </button>
          </section>

        </div>

        <!-- Right Column: Drive Integrations -->
        <div class="lg:col-span-8">
          <section class="bg-surface rounded-card p-6 shadow-[0_2px_8px_rgba(0,0,0,0.05)] border border-surface-variant h-full">
            <div class="flex flex-col sm:flex-row justify-between items-start gap-4 mb-8">
              <div>
                <h2 class="font-title-lg text-title-lg text-on-surface mb-2 flex items-center gap-2">
                  <span class="material-symbols-outlined text-primary">cloud_sync</span>
                  Repositorios de Google Drive
                </h2>
                <p class="font-body-md text-body-md text-on-surface-variant">Selecciona las carpetas para procesar los archivos académicos y vincular los webhooks.</p>
              </div>
              <span v-if="isSynced" class="px-3 py-1 rounded-full bg-primary-container/20 text-primary font-label-md text-label-md shrink-0">Sincronizado ✓</span>
              <span v-else-if="allFoldersSelected" class="px-3 py-1 rounded-full bg-secondary-container text-on-secondary-container font-label-md text-label-md shrink-0">Listo para procesar</span>
              <span v-else class="px-3 py-1 rounded-full bg-surface-container-high text-on-surface font-label-md text-label-md shrink-0">Faltan repositorios</span>
            </div>

            <!-- Folders Grid -->
            <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-10">
              
              <div 
                v-for="folder in folderList" 
                :key="folder.key"
                @click="selectFolderHandler(folder.key)"
                class="group relative rounded-xl border-2 border-dashed bg-surface-container-lowest p-6 transition-colors cursor-pointer text-center flex flex-col items-center justify-center min-h-[160px]"
                :class="folderState[folder.key]?.id ? 'border-primary' : 'border-outline-variant hover:border-primary'"
              >
                <div 
                  class="w-12 h-12 rounded-full flex items-center justify-center mb-3 transition-colors"
                  :class="folderState[folder.key]?.id ? 'bg-primary-container text-on-primary-container' : 'bg-surface-container-low group-hover:bg-primary-container group-hover:text-on-primary-container'"
                >
                  <span class="material-symbols-outlined text-[24px]">
                    {{ folder.key === 'cvs' ? 'contact_page' : (folder.key === 'syllabi' ? 'menu_book' : 'calendar_month') }}
                  </span>
                </div>
                <h3 class="font-title-md text-title-md text-on-surface mb-1">{{ folder.label }}</h3>
                <p v-if="!folderState[folder.key]?.id" class="font-body-md text-body-md text-on-surface-variant">Seleccionar carpeta</p>
                
                <!-- Selected state overlay -->
                <div v-if="folderState[folder.key]?.id" class="absolute inset-0 bg-surface-container-low rounded-xl border-2 border-primary flex flex-col items-center justify-center p-4">
                  <span class="material-symbols-outlined text-primary mb-2">folder_open</span>
                  <h3 class="font-title-md text-title-md text-on-surface text-center line-clamp-1 w-full" :title="folderState[folder.key].name">
                    {{ folderState[folder.key].name }}
                  </h3>
                  <p class="font-label-md text-label-md text-primary mt-1">Vinculado</p>
                </div>
              </div>

            </div>

            <!-- Messages -->
            <p v-if="processStatus" class="text-primary bg-primary/10 p-3 rounded-lg border border-primary/20 text-sm mt-4 font-medium mb-4 text-center">
              <span v-if="isAnyProcessing" class="material-symbols-outlined animate-spin align-middle mr-1 text-[16px]">sync</span>
              {{ processStatus }}
            </p>

            <p v-if="errorMessage" class="text-error bg-error-container p-3 rounded-lg border border-error/20 text-sm mt-4 font-medium mb-4 flex items-center gap-2">
              <span class="material-symbols-outlined">error</span> {{ errorMessage }}
            </p>

            <!-- Actions -->
            <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pt-6 border-t border-surface-variant">
              <p v-if="isSynced && allFoldersSelected" class="font-body-md text-body-md text-on-surface-variant">
                Carpetas ya vinculadas. Puedes reprocesar sin volver a seleccionarlas.
              </p>
              <div v-else class="flex-1"></div>
              <button 
                :disabled="!allFoldersSelected || isAnyProcessing"
                @click="openProcessModal"
                class="px-8 py-3 rounded-full font-label-lg text-label-lg font-medium flex items-center justify-center gap-2 shadow-sm transition-all shrink-0"
                :class="(!allFoldersSelected || isAnyProcessing) ? 'bg-surface-dim text-outline cursor-not-allowed' : 'bg-primary text-on-primary hover:opacity-90'"
              >
                <span class="material-symbols-outlined text-[20px]" :class="{'animate-spin': isAnyProcessing}">sync</span>
                <span v-if="isAnyProcessing">Procesando...</span>
                <span v-else-if="isSynced">Reprocesar</span>
                <span v-else>Procesar Todo</span>
              </button>
            </div>

          </section>
        </div>

      </div>
    </main>

    <!-- Modal de Confidencialidad -->
    <div v-if="showConfidentialityModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div class="bg-surface rounded-card p-6 md:p-8 max-w-lg w-full shadow-lg border border-surface-variant flex flex-col">
        <h3 class="font-headline-sm text-headline-sm text-on-surface mb-4 flex items-center gap-2">
          <span class="material-symbols-outlined text-primary">gavel</span>
          Términos de Confidencialidad
        </h3>
        <p class="font-body-md text-body-md text-on-surface-variant mb-6 leading-relaxed">
          Atención: El procesamiento masivo implica la lectura y estandarización de datos académicos y personales. Debe confirmar que cuenta con las autorizaciones de confidencialidad de la universidad para proceder con esta operación.
        </p>
        
        <label class="flex items-start gap-3 cursor-pointer mb-8 p-4 bg-surface-container-lowest rounded-xl border border-outline-variant hover:bg-surface-container-low transition-colors">
          <input type="checkbox" v-model="acceptedTerms" class="mt-1 w-5 h-5 text-primary rounded border-outline focus:ring-primary focus:ring-offset-surface">
          <span class="font-body-md text-body-md text-on-surface select-none">
            Confirmo que tengo los permisos necesarios y acepto la responsabilidad del tratamiento de estos datos.
          </span>
        </label>

        <div class="flex justify-end gap-3 mt-auto">
          <button @click="closeModal" class="px-6 py-2.5 rounded-full font-label-lg text-label-lg text-on-surface-variant hover:bg-surface-variant transition-colors">
            Cancelar
          </button>
          <button 
            @click="confirmAndProcess" 
            :disabled="!acceptedTerms"
            class="px-6 py-2.5 rounded-full font-label-lg text-label-lg transition-all"
            :class="acceptedTerms ? 'bg-primary text-on-primary hover:opacity-90 shadow-sm' : 'bg-surface-dim text-outline cursor-not-allowed'"
          >
            Aceptar y Procesar
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { logoutFirebase } from "../services/firebase";
import { selectFolder, processAllData } from "../services/drive";
import { exportAllRecommendations, fetchColaboradores, addColaborador, removeColaborador } from "../services/api";
import { useAppStore } from "../store/app";
import { useRouter } from "vue-router";
import { ref, computed, onMounted } from "vue";

export default {
  name: "SettingsView",

  setup() {
    const store = useAppStore();
    const router = useRouter();
    const userEmail = ref("");
    const isSynced = ref(false);
    
    // Colaboradores
    const colaboradores = ref([]);
    const nuevoColaborador = ref("");
    const cargandoColaboradores = ref(false);
    const agregandoColaborador = ref(false);
    const colaboradorError = ref("");
    
    // Estado de procesamiento individual
    const processingState = ref({
      cvs: false,
      syllabi: false,
      schedules: false
    });
    
    const exportingRecommendations = ref(false);
    
    const processStatus = ref("");
    const errorMessage = ref("");
    const showConfidentialityModal = ref(false);
    const acceptedTerms = ref(false);

    const folderState = ref({
      cvs: store.folders.cvs,
      syllabi: store.folders.syllabi,
      schedules: store.folders.schedules,
    });

    const folderList = [
      { key: "cvs", label: "CVs" },
      { key: "syllabi", label: "Sílabos" },
      { key: "schedules", label: "Horarios" },
    ];

    const allFoldersSelected = computed(() => {
      return (
        folderState.value.cvs &&
        folderState.value.syllabi &&
        folderState.value.schedules
      );
    });

    const isAnyProcessing = computed(() => {
      return Object.values(processingState.value).some(v => v);
    });

    onMounted(async () => {
      const user = auth.currentUser;
      if (user) {
        userEmail.value = user.email || "Usuario";
      }

      folderState.value = {
        cvs: store.folders.cvs,
        syllabi: store.folders.syllabi,
        schedules: store.folders.schedules,
      };

      // Verificar sincronización previa
      const syncedStr = localStorage.getItem('teacher_ideal_synced_folders');
      if (syncedStr) {
        try {
          const syncedData = JSON.parse(syncedStr);
          if (
            syncedData.cvs === folderState.value.cvs?.id &&
            syncedData.syllabi === folderState.value.syllabi?.id &&
            syncedData.schedules === folderState.value.schedules?.id &&
            folderState.value.cvs?.id
          ) {
            isSynced.value = true;
          }
        } catch (e) {
          console.error("Error parseando synced folders:", e);
        }
      }

      await loadColaboradores();
    });

    const goBack = () => {
      if (store.hasData) {
        router.push('/ciclos');
      } else {
        router.push('/home');
      }
    };

    const logout = async () => {
      try {
        await logoutFirebase();
        store.clearState();
        router.push('/login');
      } catch (error) {
        console.error("Error cerrando sesión:", error);
      }
    };

    const loadColaboradores = async () => {
      try {
        cargandoColaboradores.value = true;
        colaboradorError.value = "";
        colaboradores.value = await fetchColaboradores();
      } catch (err) {
        colaboradorError.value = "Error al cargar colaboradores";
      } finally {
        cargandoColaboradores.value = false;
      }
    };

    const handleAddColaborador = async () => {
      if (!nuevoColaborador.value.trim()) return;
      try {
        agregandoColaborador.value = true;
        colaboradorError.value = "";
        await addColaborador(nuevoColaborador.value.trim());
        nuevoColaborador.value = "";
        await loadColaboradores();
      } catch (err) {
        colaboradorError.value = err.message || "Error al añadir colaborador";
      } finally {
        agregandoColaborador.value = false;
      }
    };

    const handleRemoveColaborador = async (email) => {
      if (!confirm(`¿Eliminar al colaborador ${email}?`)) return;
      try {
        colaboradorError.value = "";
        await removeColaborador(email);
        await loadColaboradores();
      } catch (err) {
        colaboradorError.value = err.message || "Error al eliminar colaborador";
      }
    };

    const handleExportRecommendations = async () => {
      exportingRecommendations.value = true;
      errorMessage.value = "";
      try {
        await exportAllRecommendations();
      } catch (error) {
        alert("Error exportando recomendaciones: " + error.message);
      } finally {
        exportingRecommendations.value = false;
      }
    };

    const selectFolderHandler = async (type) => {
      try {
        errorMessage.value = "";
        const folder = await selectFolder(type);
        
        if (folder) {
          folderState.value[type] = folder;
          store.setFolder(type, folder);
          
          // Limpiar localstorage y habilitar boton
          const syncedStr = localStorage.getItem('teacher_ideal_synced_folders');
          if (syncedStr) {
            try {
              const syncedData = JSON.parse(syncedStr);
              delete syncedData[type];
              localStorage.setItem('teacher_ideal_synced_folders', JSON.stringify(syncedData));
            } catch(e) {}
          }
          isSynced.value = false;
        }
      } catch (error) {
        console.error(`Error seleccionando carpeta ${type}:`, error);
        errorMessage.value = `Error seleccionando carpeta: ${error.message}`;
      }
    };

    const getGoogleToken = () => {
      const token = localStorage.getItem('googleToken');
      if (!token) throw new Error("No se encontró el token de Google. Inicia sesión nuevamente.");
      return token;
    };

    const openProcessModal = () => {
      // Permitir reprocesar con carpetas ya vinculadas (isSynced solo indica que ya se configuró una vez).
      if (!allFoldersSelected.value || isAnyProcessing.value) return;
      acceptedTerms.value = false;
      showConfidentialityModal.value = true;
    };

    const closeModal = () => {
      showConfidentialityModal.value = false;
      acceptedTerms.value = false;
    };

    const confirmAndProcess = () => {
      showConfidentialityModal.value = false;
      processData();
    };

    const processData = async () => {
      if (!allFoldersSelected.value) {
        errorMessage.value = "Falta seleccionar una o más carpetas.";
        return;
      }

      try {
        processingState.value.cvs = true;
        processingState.value.syllabi = true;
        processingState.value.schedules = true;
        
        errorMessage.value = "";
        processStatus.value = "Iniciando configuración secuencial...";

        const token = getGoogleToken();
        
        processStatus.value = `Procesando carpetas sincrónicamente...`;
        const result = await processAllData(folderState.value);
        
        if (!result.success) {
            throw new Error(`Error vinculando carpetas: ${result.error || 'Desconocido'}`);
        }

        processStatus.value = "✅ Configuración guardada y webhooks activos.";
        
        // Guardar exitosos en localStorage
        const syncedData = {
          cvs: folderState.value.cvs.id,
          syllabi: folderState.value.syllabi.id,
          schedules: folderState.value.schedules.id
        };
        localStorage.setItem('teacher_ideal_synced_folders', JSON.stringify(syncedData));
        isSynced.value = true;

        setTimeout(() => {
          router.push('/ciclos');
        }, 1500);
        
      } catch (error) {
        console.error("Error procesando archivos:", error);
        errorMessage.value = error.message;
        processStatus.value = "";
      } finally {
        processingState.value.cvs = false;
        processingState.value.syllabi = false;
        processingState.value.schedules = false;
      }
    };

    return {
      userEmail,
      folderState,
      folderList,
      allFoldersSelected,
      processingState,
      isAnyProcessing,
      processStatus,
      errorMessage,
      goBack,
      logout,
      handleExportRecommendations,
      exportingRecommendations,
      selectFolderHandler,
      processData,
      openProcessModal,
      closeModal,
      confirmAndProcess,
      showConfidentialityModal,
      acceptedTerms,
      isSynced,
      colaboradores,
      nuevoColaborador,
      cargandoColaboradores,
      agregandoColaborador,
      colaboradorError,
      handleAddColaborador,
      handleRemoveColaborador
    };
  },
};
</script>