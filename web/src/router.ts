import { createRouter, createWebHashHistory } from "vue-router";

import Home from "@/pages/Home.vue";
import Methodology from "@/pages/Methodology.vue";
import QualityControl from "@/pages/QualityControl.vue";

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
