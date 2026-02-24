export const tags = {
    authentication: "Authentication",
    javascript: "JavaScript",
    nodejs: "Node.js",
    python: "Python",
    html: "HTML",
    css: "CSS",
    react: "React",
    astro: "Astro",
    nextjs: "Next.js",
    typescript: "TypeScript",
    expo: "Expo",
    mobile: "Mobile Development",
    web: "Web Development",
    api: "API Development",
    database: "Database",
    devops: "DevOps",
    testing: "Testing",
    security: "Security",
    performance: "Performance Optimization",
    reactnative: "React Native",
    supabase: "Supabase",
    bigcommerce: "BigCommerce",
    authjs: "Auth.js",
    php: "PHP",
    cms: "CMS",
    office365: "Office 365"
} as const;

export type TagItem = keyof typeof tags;

export const categories = {
    apps: "Apps",
    websites: "Websites",
    integrations: "Integrations"
} as const;

export type Category = keyof typeof categories;