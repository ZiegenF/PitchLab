import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import NavBar from "./components/NavBar";
import AuthPage from "./pages/AuthPage";
import DugoutPage from "./pages/DugoutPage";
import PlayerPage from "./pages/PlayerPage";
import ScoutPage from "./pages/ScoutPage";

function Home() {
  const { user, loading } = useAuth();
  if (loading) return null;
  return <Navigate to={user ? "/dugout" : "/scout"} replace />;
}

export default function App() {
  return (
    <>
      <NavBar />
      <main className="page">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/dugout" element={<DugoutPage />} />
          <Route path="/scout" element={<ScoutPage />} />
          <Route path="/players/:id" element={<PlayerPage />} />
          <Route path="/login" element={<AuthPage mode="login" />} />
          <Route path="/signup" element={<AuthPage mode="signup" />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </>
  );
}
