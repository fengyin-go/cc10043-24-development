import { createRouter, createWebHistory } from 'vue-router'

import Overview from '@/views/Overview.vue'
import WorkbenchView from '@/views/WorkbenchView.vue'
import FieldTransformImpactView from '@/views/FieldTransformImpactView.vue'
import SchemaImpactView from '@/views/SchemaImpactView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: Overview },
    {
      path: '/field_transform/impact',
      name: 'field-transform-impact',
      component: FieldTransformImpactView,
    },
    {
      path: '/schema_registry/impact',
      name: 'schema-registry-impact',
      component: SchemaImpactView,
    },
    { path: '/:moduleKey', name: 'module', component: WorkbenchView, props: true },
  ],
})

export default router
