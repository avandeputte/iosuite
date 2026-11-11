---
description: ioRecipe, the family's recipes in the ioThing suite.
---

# ioRecipe <small>recipes</small>

The family's recipe book: a web app to keep recipes with their ingredients, steps and a photo, and to bring one in
from the web by pasting its address.

## What it does

- **Recipes** with a description, what they make, preparation and cooking time, ingredients, steps, notes and tags.
  A line that ends with a colon ("For the icing:") is a heading.
- **A photo** for each recipe, uploaded from the computer or taken with the phone.
- **Import from the web**: paste the address of a recipe page and ioRecipe keeps the recipe it describes (title,
  ingredients, steps, times, tags) with its picture and a link back. It reads the recipe data most recipe sites
  publish for search engines; where a page has none, add the recipe by hand.
- **The recipes as cards**, with their photo and how long they take: all of them, the family's, your own, or by tag;
  search looks in the titles, the ingredients, the steps and the tags.
- **Cooking from it**: tick the ingredients off as they go in, strike a step out when it is done, or print the recipe.
- **Family and private recipes**: everyone sees the family's; a private one is yours alone. Viewers read, members
  keep their own, editors change the family's.
- **Everywhere**: a REST API with OpenAPI docs at `/api/docs`, and an MCP server for AI assistants.

## On its own

ioRecipe is a complete recipe book for a family. It needs its database and the Shared ioSuite database; the photos
are kept in the database too, so there is nothing else to back up.

## With the other apps

- **ioSuite**: a tile on the start page, and one sign-in for all the apps.

## Install

| | |
| --- | --- |
| Proxmox VE | `bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iorecipe/main/proxmox/ct/iorecipe.sh)"` |
| Docker | [docker-compose.yml](https://github.com/avandeputte/iorecipe/blob/main/docker-compose.yml): the image `ghcr.io/avandeputte/iorecipe` |
| Any Linux or Mac | `git clone https://github.com/avandeputte/iorecipe && cd iorecipe && ./setup.sh` |
| Port | 8690 |
| Source | [github.com/avandeputte/iorecipe](https://github.com/avandeputte/iorecipe) |
