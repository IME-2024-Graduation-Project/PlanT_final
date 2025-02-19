/*!

=========================================================
* Paper Dashboard React - v1.3.2
=========================================================

* Product Page: https://www.creative-tim.com/product/paper-dashboard-react
* Copyright 2023 Creative Tim (https://www.creative-tim.com)

* Licensed under MIT (https://github.com/creativetimofficial/paper-dashboard-react/blob/main/LICENSE.md)

* Coded by Creative Tim

=========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

*/
import React from "react";
import { NavLink, useLocation } from "react-router-dom";
import { Nav } from "reactstrap";
// javascript plugin used to create scrollbars on windows
import PerfectScrollbar from "perfect-scrollbar";

import logo from "plant.png";

var ps;

function Sidebar(props) {
  const location = useLocation();
  const sidebar = React.useRef();
  // verifies if routeName is the one active (in browser input)
  const activeRoute = (routeName) => {
    return location.pathname.indexOf(routeName) > -1 ? "active" : "";
  };
  React.useEffect(() => {
    if (navigator.platform.indexOf("Win") > -1) {
      ps = new PerfectScrollbar(sidebar.current, {
        suppressScrollX: true,
        suppressScrollY: false,
      });
    }
    return function cleanup() {
      if (navigator.platform.indexOf("Win") > -1) {
        ps.destroy();
      }
    };
  });
  return (
    <div
      className="sidebar"
      data-color="white"
      data-active-color="success"
    >
      <div className="logo">
        <a
          href="http://localhost:3000/admin/mypage"
          className="simple-text logo-mini"
        >
          <div className="logo-img">
            <img src={logo} alt="react-logo" />
          </div>
        </a>
        <a
          href="http://localhost:3000/admin/mypage"
          className="simple-text logo-normal"
        >
          PlanT
        </a>
      </div>
      <div className="sidebar-wrapper" ref={sidebar}>
      <Nav>
        {props.routes.map((prop, key) => {
          // hidden 속성이 있는지 확인하고, 있으면 해당 경로를 숨깁니다.
          if (prop.hidden) {
            return null;
          }
          return (
            <li
              className={
                activeRoute(prop.path) + (prop.pro ? " active-pro" : "")
              }
              key={key}
            >
              {prop.name === "Output Page" ? (
                  <NavLink className="nav-NavLink">
                  <p>{prop.name}</p>
                </NavLink>
                ) : (
                  <NavLink to={prop.layout + prop.path} className="nav-NavLink">
                    <p>{prop.name}</p>
                  </NavLink>
                )}
            </li>
          );
        })}
      </Nav>
      </div>
    </div>
  );
}

export default Sidebar;
