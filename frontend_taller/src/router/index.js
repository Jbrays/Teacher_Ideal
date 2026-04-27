import { createRouter, createWebHistory } from 'vue-router';
import { auth } from '../services/firebase';
import { onAuthStateChanged } from 'firebase/auth';

import LoginView from '../views/LoginView.vue';
import HomeView from '../views/HomeView.vue';
import SettingsView from '../views/SettingsView.vue';
import CiclosView from '../views/CiclosView.vue';
import CursosView from '../views/CursosView.vue';
import RecomendacionesView from '../views/RecomendacionesView.vue';

const routes = [
  { path: '/', redirect: '/login' },
  { path: '/login', name: 'login', component: LoginView, meta: { requiresAuth: false } },
  { path: '/home', name: 'home', component: HomeView, meta: { requiresAuth: true } },
  { path: '/settings', name: 'settings', component: SettingsView, meta: { requiresAuth: true } },
  { path: '/ciclos', name: 'ciclos', component: CiclosView, meta: { requiresAuth: true } },
  { path: '/cursos/:cicloId', name: 'cursos', component: CursosView, meta: { requiresAuth: true } },
  { path: '/recomendaciones/:cursoId', name: 'recomendaciones', component: RecomendacionesView, meta: { requiresAuth: true } },
];

const router = createRouter({
  history: createWebHistory(),
  routes
});

// Función para obtener el usuario actual de manera asíncrona
const getCurrentUser = () => {
  return new Promise((resolve, reject) => {
    const unsubscribe = onAuthStateChanged(
      auth,
      (user) => {
        unsubscribe();
        resolve(user);
      },
      reject
    );
  });
};

// Guard de navegación global
router.beforeEach(async (to, from, next) => {
  const requiresAuth = to.meta.requiresAuth;
  
  // Esperar a que Firebase determine el estado de autenticación
  const currentUser = await getCurrentUser();

  // Si la ruta requiere autenticación y no hay usuario
  if (requiresAuth && !currentUser) {
    console.log('🔒 Ruta protegida, redirigiendo al login');
    next('/login');
  } 
  // Si está autenticado e intenta ir al login, redirigir a home
  else if (to.path === '/login' && currentUser) {
    console.log('✅ Usuario ya autenticado, redirigiendo a home');
    next('/home');
  }
  // En cualquier otro caso, continuar
  else {
    next();
  }
});

export default router;

