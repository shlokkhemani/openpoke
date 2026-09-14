import { NavLink, Outlet } from 'react-router-dom'

export default function App() {
  return (
    <div className="shell">
      <nav className="nav">
        <div className="brand">OpenPoke Evals<span>end-to-end overload suite</span></div>
        <NavLink to="/runs" className={({ isActive }) => (isActive ? 'active' : '')}>Runs</NavLink>
        <NavLink to="/cases" className={({ isActive }) => (isActive ? 'active' : '')}>Test cases</NavLink>
      </nav>
      <main className="main"><Outlet /></main>
    </div>
  )
}
