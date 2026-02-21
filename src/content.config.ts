import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { z } from 'astro/zod';

const projects = defineCollection({
    loader: glob({pattern: '**.md', base: './src/data/projects'}),
    schema: z.object({
        title: z.string(),
        description: z.string(),
        category: z.string(),
        featured: z.boolean(),
        image: z.string(),
        thumb: z.string(),
        created: z.string(),
        updated: z.string(),
        tags: z.array(z.string())
    }),
});

export const collections = {
    projects,
};