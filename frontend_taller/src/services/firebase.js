import { initializeApp } from "firebase/app";
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signOut
} from "firebase/auth";

import firebaseConfig from './firebaseConfig'; // archivo separado

// Inicializar Firebase inmediatamente
const app = initializeApp(firebaseConfig);
const auth = getAuth(app);

export async function loginWithGoogle() {
  const provider = new GoogleAuthProvider();

  // IMPORTANTE: permisos para Drive
  provider.addScope('https://www.googleapis.com/auth/drive.readonly');

  const result = await signInWithPopup(auth, provider);
  const credential = GoogleAuthProvider.credentialFromResult(result);

  return {
    user: result.user,
    googleToken: credential.accessToken
  };
}

export async function logoutFirebase() {
  return await signOut(auth);
}

export { auth };
