import { initializeApp } from "firebase/app";
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signOut
} from "firebase/auth";
import { getFirestore } from "firebase/firestore";

import firebaseConfig from './firebaseConfig';
import { apiURL } from './api';

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const db = getFirestore(app);

const DRIVE_SCOPE = 'https://www.googleapis.com/auth/drive.readonly';

// Client ID del OAuth de Google (mismo del IdP Firebase). Público por diseño.
const GOOGLE_OAUTH_CLIENT_ID =
  import.meta.env.VITE_GOOGLE_OAUTH_CLIENT_ID ||
  '637375097598-91mm9fnkk3lbi1nr88drh9moiskr128b.apps.googleusercontent.com';

function loadGisScript() {
  return new Promise((resolve, reject) => {
    if (window.google?.accounts?.oauth2) {
      resolve();
      return;
    }
    const existing = document.querySelector('script[data-gis="1"]');
    if (existing) {
      existing.addEventListener('load', () => resolve());
      existing.addEventListener('error', reject);
      return;
    }
    const s = document.createElement('script');
    s.src = 'https://accounts.google.com/gsi/client';
    s.async = true;
    s.dataset.gis = '1';
    s.onload = () => resolve();
    s.onerror = reject;
    document.head.appendChild(s);
  });
}

async function getFirebaseAuthHeaders() {
  const user = auth.currentUser;
  if (!user) throw new Error('No hay sesión Firebase');
  const token = await user.getIdToken();
  return {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  };
}

/**
 * Solicita authorization code offline (refresh_token) y lo envía al backend.
 * Con access_type=offline + prompt=consent Google emite refresh_token;
 * el backend lo guarda y renueva access_token solo, sin que el usuario vuelva a entrar.
 * La sesión de Drive solo se borra al cerrar sesión (logoutFirebase).
 */
export async function authorizeDriveOffline({ forceConsent = true } = {}) {
  await loadGisScript();

  return new Promise((resolve, reject) => {
    try {
      const client = window.google.accounts.oauth2.initCodeClient({
        client_id: GOOGLE_OAUTH_CLIENT_ID,
        scope: DRIVE_SCOPE,
        ux_mode: 'popup',
        // Offline = refresh_token en el intercambio del code (backend)
        access_type: 'offline',
        // consent fuerza refresh_token aunque el usuario ya hubiera autorizado antes
        prompt: forceConsent ? 'consent' : '',
        callback: async (response) => {
          try {
            if (response.error) {
              reject(new Error(response.error));
              return;
            }
            if (!response.code) {
              reject(new Error('Google no devolvió authorization code'));
              return;
            }
            const headers = await getFirebaseAuthHeaders();
            const res = await fetch(apiURL('/api/auth/drive/code'), {
              method: 'POST',
              headers,
              body: JSON.stringify({ code: response.code }),
            });
            if (!res.ok) {
              const err = await res.json().catch(() => ({}));
              throw new Error(err.detail || `Error ${res.status} guardando tokens Drive`);
            }
            const data = await res.json();
            console.log('✅ Drive offline autorizado', data);
            if (!data.has_refresh_token) {
              console.warn(
                '⚠️ Google no devolvió refresh_token. El procesamiento largo puede fallar al caducar el access_token.'
              );
            }
            resolve(data);
          } catch (e) {
            reject(e);
          }
        },
      });
      client.requestCode();
    } catch (e) {
      reject(e);
    }
  });
}

/**
 * Renueva access_token de Drive en el cliente y lo sincroniza al backend
 * (también refresca con GIS sin UI si ya hay consentimiento).
 */
export async function refreshAndSyncDriveAccessToken() {
  await loadGisScript();

  return new Promise((resolve, reject) => {
    const client = window.google.accounts.oauth2.initTokenClient({
      client_id: GOOGLE_OAUTH_CLIENT_ID,
      scope: DRIVE_SCOPE,
      callback: async (response) => {
        try {
          if (response.error) {
            reject(new Error(response.error));
            return;
          }
          const accessToken = response.access_token;
          if (!accessToken) {
            reject(new Error('Sin access_token de Drive'));
            return;
          }
          localStorage.setItem('googleToken', accessToken);
          localStorage.setItem(
            'googleToken_expires_at',
            String(Date.now() + ((response.expires_in || 3600) - 120) * 1000)
          );

          if (auth.currentUser) {
            const headers = await getFirebaseAuthHeaders();
            await fetch(apiURL('/api/auth/drive/token'), {
              method: 'POST',
              headers,
              body: JSON.stringify({
                access_token: accessToken,
                expires_in: response.expires_in || 3600,
              }),
            });
          }
          resolve(accessToken);
        } catch (e) {
          reject(e);
        }
      },
    });
    // Sin prompt si ya se concedió antes
    client.requestAccessToken({ prompt: '' });
  });
}

export async function loginWithGoogle() {
  const provider = new GoogleAuthProvider();
  provider.addScope(DRIVE_SCOPE);
  provider.setCustomParameters({
    access_type: 'offline',
    prompt: 'select_account',
  });

  const result = await signInWithPopup(auth, provider);
  const credential = GoogleAuthProvider.credentialFromResult(result);
  const accessToken = credential?.accessToken || null;

  if (accessToken) {
    localStorage.setItem('googleToken', accessToken);
    localStorage.setItem('googleToken_expires_at', String(Date.now() + 55 * 60 * 1000));
  }

  // Tras Firebase, pide autorización offline de Drive (refresh_token en backend)
  try {
    await authorizeDriveOffline();
  } catch (e) {
    console.warn('No se pudo completar OAuth offline de Drive (se intentará con access token):', e);
    // Seed access token en backend de todos modos
    if (accessToken && result.user) {
      try {
        const idToken = await result.user.getIdToken();
        await fetch(apiURL('/api/auth/drive/token'), {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${idToken}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ access_token: accessToken, expires_in: 3600 }),
        });
      } catch (err) {
        console.warn('No se pudo enviar access_token al backend', err);
      }
    }
  }

  // Keepalive: renueva access token en backend cada 40 min mientras la pestaña viva
  startDriveTokenKeepAlive();

  return {
    user: result.user,
    googleToken: accessToken || localStorage.getItem('googleToken'),
  };
}

let keepAliveTimer = null;

export function startDriveTokenKeepAlive() {
  if (keepAliveTimer) return;
  keepAliveTimer = setInterval(async () => {
    if (!auth.currentUser) return;
    try {
      await refreshAndSyncDriveAccessToken();
    } catch (e) {
      console.warn('Keepalive Drive falló (se reintentará):', e.message || e);
    }
  }, 40 * 60 * 1000);
}

export function stopDriveTokenKeepAlive() {
  if (keepAliveTimer) {
    clearInterval(keepAliveTimer);
    keepAliveTimer = null;
  }
}

export async function logoutFirebase() {
  stopDriveTokenKeepAlive();
  try {
    if (auth.currentUser) {
      const headers = await getFirebaseAuthHeaders();
      await fetch(apiURL('/api/auth/drive/token'), { method: 'DELETE', headers });
    }
  } catch (e) {
    console.warn('No se pudieron borrar tokens Drive en backend', e);
  }
  localStorage.removeItem('googleToken');
  localStorage.removeItem('googleToken_expires_at');
  localStorage.removeItem('firebase_id_token');
  return await signOut(auth);
}

export { auth, db, GOOGLE_OAUTH_CLIENT_ID };
