import { defineStore } from 'pinia';
import { fetchCursos, fetchRecommendations } from '../services/api';

const APP_STATE_KEY = 'appState';

export const useAppStore = defineStore('app', {
  state: () => ({
    user: null,
    googleAccessToken: null,
    firebaseIdToken: null,

    folders: {
      cvs: null,
      syllabi: null,
      schedules: null
    },

    data: {
      docentes: [],
      ciclos: [],
      cursos: {}
    },

    currentCiclo: null,
    currentCurso: null,
    currentCursoNombre: null,
    recommendations: [],
  }),

  getters: {
    ciclos: (state) => state.data.ciclos || [],

    cursosDelCiclo: (state) => {
      if (!state.currentCiclo) return [];
      return state.data.cursos[state.currentCiclo] || [];
    },

    // Corregido para que 'schedules' sea opcional
    allFoldersSelected: (state) => {
      return !!(state.folders.cvs && state.folders.syllabi);
    },

    hasData: (state) => {
      return state.data.ciclos.length > 0;
    }
  },

  actions: {
    // ==================== USER & AUTH ====================

    setUser(user) {
      this.user = user;
      this.saveState();
    },

    setTokens({ google, firebase }) {
      this.googleAccessToken = google;
      this.firebaseIdToken = firebase;

      // Persistencia de tokens
      if (google) localStorage.setItem('googleToken', google);
      if (firebase) localStorage.setItem('firebase_id_token', firebase);
    },

    // ==================== FOLDERS ====================

    setFolders(folders) {
      this.folders = { ...this.folders, ...folders };
      this.saveState();
    },

    setFolder(type, folder) {
      this.folders[type] = folder;
      this.saveState();
    },

    // ==================== DATA ====================

    setData(data) {
      if (data.docentes) this.data.docentes = data.docentes;
      if (data.ciclos) this.data.ciclos = data.ciclos;
      if (data.cursos) this.data.cursos = data.cursos;
      this.saveState();
    },

    /**
     * Cargar cursos desde el backend
     */
    async loadCursosFromBackend() {
      try {
        console.log('📥 Cargando cursos del backend...');

        // Esta lógica es CORRECTA porque 'api.js' (de mi mensaje anterior)
        // devuelve el objeto JSON completo.
        const response = await fetchCursos();

        // Este log es para tu debug
        console.log("👇 RESPUESTA CRUDA RECIBIDA (Cursos):", response);

        if (!response || !response.success) {
          throw new Error("La API no pudo obtener los cursos");
        }

        // Accedemos a la propiedad .cursos del objeto
        const cursosData = response.cursos;

        if (cursosData && cursosData.length > 0) {
          // Organizar cursos por ciclo
          const ciclos = [];
          const cursosPorCiclo = {};

          cursosData.forEach(curso => {
            const ciclo = curso.ciclo ? String(curso.ciclo) : '1';

            if (!cursosPorCiclo[ciclo]) {
              cursosPorCiclo[ciclo] = [];
              ciclos.push(ciclo);
            }

            cursosPorCiclo[ciclo].push(curso);
          });

          ciclos.sort((a, b) => parseInt(a) - parseInt(b));

          this.data.ciclos = ciclos;
          this.data.cursos = cursosPorCiclo;

          console.log(`✅ ${cursosData.length} cursos cargados en ${ciclos.length} ciclos`);
          this.saveState();
          return true;
        }

        console.log('⚠️ No hay cursos en el backend');
        return false;
      } catch (error) {
        console.error('❌ Error cargando cursos:', error);
        throw error;
      }
    },

    /**
     * Cargar recomendaciones para un curso
     */
    async fetchRecommendations() {
      if (!this.currentCurso) {
        console.error('No hay curso seleccionado');
        return;
      }

      try {
        console.log(`🤖 Obteniendo recomendaciones para curso ${this.currentCurso}...`);

        // Esta lógica es CORRECTA porque 'api.js' (de mi mensaje anterior)
        // devuelve el objeto JSON completo.
        const response = await fetchRecommendations(this.currentCurso, 100);

        // Este log es para tu debug
        console.log("👇 RESPUESTA CRUDA RECIBIDA (Recomendaciones):", response);

        if (!response || !response.success) {
          throw new Error("La API no pudo obtener las recomendaciones");
        }

        // Accedemos a la propiedad .recommendations del objeto
        const recommendations = response.recommendations;

        this.recommendations = recommendations;
        // Esta línea ya no dará 'undefined'
        console.log(`✅ ${recommendations.length} recomendaciones obtenidas`);
        this.saveState();

        return recommendations;
      } catch (error) {
        console.error('❌ Error obteniendo recomendaciones:', error);
        throw error;
      }
    },

    // ==================== NAVIGATION ====================

    goToCursos(ciclo) {
      this.currentCiclo = ciclo;
      this.saveState();
      return `/cursos/${ciclo}`;
    },

    goToRecommendations(curso) {
      this.currentCiclo = curso.ciclo || this.currentCiclo;
      this.currentCurso = curso.id;
      this.currentCursoNombre = curso.nombre;
      this.recommendations = []; // Reset
      this.saveState();
      return `/recomendaciones/${curso.id}`;
    },

    // ==================== PERSISTENCE ====================

    saveState() {
      try {
        const state = {
          folders: this.folders,
          data: this.data,
          currentCiclo: this.currentCiclo,
          currentCurso: this.currentCurso,
          currentCursoNombre: this.currentCursoNombre,
          recommendations: this.recommendations,
        };
        localStorage.setItem(APP_STATE_KEY, JSON.stringify(state));
      } catch (error) {
        console.error('Error guardando estado:', error);
      }
    },

    restoreState() {
      try {
        const saved = localStorage.getItem(APP_STATE_KEY);
        if (saved) {
          const state = JSON.parse(saved);

          this.folders = state.folders || this.folders;
          this.data = state.data || this.data;
          this.currentCiclo = state.currentCiclo;
          this.currentCurso = state.currentCurso;
          this.currentCursoNombre = state.currentCursoNombre;
          this.recommendations = state.recommendations || [];

          console.log('✅ Estado restaurado desde localStorage');
          return true;
        }
      } catch (error) {
        console.error('Error restaurando estado:', error);
      }
      return false;
    },

    clearState() {
      this.folders = { cvs: null, syllabi: null, schedules: null };
      this.data = { docentes: [], ciclos: [], cursos: {} };
      this.currentCiclo = null;
      this.currentCurso = null;
      this.currentCursoNombre = null;
      this.recommendations = [];
      localStorage.removeItem(APP_STATE_KEY);
    }
  }
});