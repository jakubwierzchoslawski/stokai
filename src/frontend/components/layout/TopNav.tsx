/**
 * TopNav — top navigation bar for the StokAI application.
 *
 * Contains navigation links including the Company Screener entry point (AC-001).
 * Uses React Router NavLink for active-state styling.
 */
import React from "react";
import { NavLink } from "react-router-dom";

export function TopNav() {
  return (
    <nav className="top-nav" aria-label="Main navigation">
      <div className="top-nav__brand">
        <NavLink to="/" className="top-nav__brand-link" aria-label="StokAI home">
          StokAI
        </NavLink>
      </div>

      <ul className="top-nav__links" role="list">
        <li className="top-nav__item">
          <NavLink
            to="/map"
            className={({ isActive }) =>
              `top-nav__link${isActive ? " top-nav__link--active" : ""}`
            }
          >
            Intelligence Map
          </NavLink>
        </li>
        <li className="top-nav__item">
          <NavLink
            to="/screener"
            className={({ isActive }) =>
              `top-nav__link${isActive ? " top-nav__link--active" : ""}`
            }
          >
            Screener
          </NavLink>
        </li>
        <li className="top-nav__item">
          {/* PLAN-F-026 TASK-008 — Briefs and Reports Reader navigation */}
          <NavLink
            to="/briefs"
            className={({ isActive }) =>
              `top-nav__link${isActive ? " top-nav__link--active" : ""}`
            }
          >
            Briefs
          </NavLink>
        </li>
      </ul>
    </nav>
  );
}

export default TopNav;
