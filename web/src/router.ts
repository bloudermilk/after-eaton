import { createRouter, createWebHashHistory } from "vue-router";

// Lazily loaded so the heavy map dependency (maplibre-gl, pulled in by Home)
// is code-split into its own chunk instead of bloating the initial bundle.
const Home = () => import("@/pages/Home.vue");
const Methodology = () => import("@/pages/Methodology.vue");
const QualityControl = () => import("@/pages/QualityControl.vue");

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: "/", name: "home", component: Home, meta: { title: "Home" } },
    {
      path: "/methodology",
      name: "methodology",
      component: Methodology,
      meta: { title: "Methodology" },
    },
    {
      path: "/quality-control",
      name: "quality-control",
      component: QualityControl,
      meta: { title: "Quality Control" },
    },
  ],
  scrollBehavior(_to, _from, savedPosition) {
    return savedPosition ?? { top: 0 };
  },
});
