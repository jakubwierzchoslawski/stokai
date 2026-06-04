/**
 * AdminNav — navigation links for the admin section.
 *
 * Links:
 *   - HIL Review Queue (/admin/hil)
 *   - Data Sources (/admin/sources)
 *
 * PLAN-F-028 TASK-011
 */
import React from "react";
import { NavLink } from "react-router-dom";

export const AdminNav: React.FC = () => {
  return (
    <nav className="admin-nav" aria-label="Admin navigation" data-testid="admin-nav">
      <ul className="admin-nav__list">
        <li>
          <NavLink
            to="/admin/hil"
            className={({ isActive }) =>
              `admin-nav__link ${isActive ? "admin-nav__link--active" : ""}`
            }
            data-testid="nav-hil"
          >
            HIL Review Queue
          </NavLink>
        </li>
        <li>
          <NavLink
            to="/admin/sources"
            className={({ isActive }) =>
              `admin-nav__link ${isActive ? "admin-nav__link--active" : ""}`
            }
            data-testid="nav-sources"
          >
            Data Sources
          </NavLink>
        </li>
      </ul>
    </nav>
  );
};

export default AdminNav;
