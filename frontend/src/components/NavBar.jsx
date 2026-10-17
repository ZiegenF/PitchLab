import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import Logo from "./Logo";

// The scoreboard across the top of every page.
export default function NavBar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <header className="navbar">
      <div className="navbar-inner">
        <Link to="/" className="brand">
          <Logo size={30} />
          <span>PitchLab</span>
        </Link>
        <nav className="nav-links">
          <NavLink to="/dugout">My Dugout</NavLink>
          <NavLink to="/scout">Scout Players</NavLink>
        </nav>
        <div className="nav-user">
          {user ? (
            <>
              <span className="nav-name">{user.display_name}</span>
              <button
                className="btn on-board"
                onClick={async () => {
                  await logout();
                  navigate("/scout");
                }}
              >
                Sign out
              </button>
            </>
          ) : (
            <>
              <Link className="btn on-board" to="/login">
                Sign in
              </Link>
              <Link className="btn primary" to="/signup">
                Create account
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
