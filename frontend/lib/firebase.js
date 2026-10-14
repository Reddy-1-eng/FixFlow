import { initializeApp, getApps, getApp } from "firebase/app";
import {
  getAuth,
  GoogleAuthProvider,
  GithubAuthProvider,
  signInWithPopup,
  signOut as firebaseSignOut,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  updateProfile
} from "firebase/auth";

const firebaseConfig = {
  projectId: "fixflow-beb5b",
  appId: "1:1054104343503:web:f058d06f16965c579ab8ba",
  databaseURL: "https://fixflow-beb5b-default-rtdb.asia-southeast1.firebasedatabase.app",
  storageBucket: "fixflow-beb5b.firebasestorage.app",
  apiKey: "AIzaSyAsVzX8RLreLOC6h_EVkcXqBfCZstfYr1E",
  authDomain: "fixflow-beb5b.firebaseapp.com",
  messagingSenderId: "1054104343503"
};

const app = getApps().length > 0 ? getApp() : initializeApp(firebaseConfig);
const auth = getAuth(app);
const googleProvider = new GoogleAuthProvider();
const githubProvider = new GithubAuthProvider();

export {
  app,
  auth,
  googleProvider,
  githubProvider,
  signInWithPopup,
  firebaseSignOut,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  updateProfile
};
