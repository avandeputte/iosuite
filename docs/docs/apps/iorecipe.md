---
description: ioRecipe, the family's recipes in the ioThing suite.
---

# ioRecipe <small>recipes</small>

The family's recipe book: a web app to keep recipes with their ingredients, steps and photos, to bring one in from
the web, from pasted text, from a photo or from a file, and to cook, shop and print from it.

## What it does

- **Recipes** with a description, what they make, preparation and cooking time, ingredients, steps, notes and tags.
  A line that ends with a colon ("For the icing:") is a heading.
- **Photos**: as many as you like for a recipe, and one for any step, uploaded from the computer or taken with the
  phone.
- **Import from the web**: paste the address of a recipe page and ioRecipe keeps the recipe it describes (title,
  ingredients, steps, times, tags) with its picture and a link back. It reads the recipe data most recipe sites
  publish for search engines; on a page without it, the page's own lists and the text under "Ingredients". A page
  that still gives no complete recipe is read by a small AI model that runs inside the app, on your own server:
  nothing is sent to an AI service. The picture is downloaded and kept with the recipe, so it stays when the page
  goes away.
- **Import from pasted text or a photo**: paste a recipe from a message or a document, or give a photo of a page of
  a cookbook. The text becomes a draft in the recipe form, for you to look over before it is saved. A photo is read
  on your own server (by Tesseract); it goes nowhere else.
- **Export and import as a file**: one recipe, a cookbook or everything as a `.zip`, to keep safe or to move to
  another ioRecipe. The import also takes recipes and backups from Mealie.
- **The recipes as cards**, with their photo and how long they take: all of them, the family's, your own, your
  favourites, by tag or by cookbook; search looks in the titles, the ingredients, the steps and the tags.
- **Favourites and ratings**: a heart and one to five stars, yours alone; everyone sees the average.
- **Cookbooks**: recipes grouped under a name, the family's or your own.
- **Cooking from it**: the amounts follow the servings you want, tick the ingredients off as they go in, strike a
  step out when it is done, or print the recipe.
- **Family and private recipes**: everyone sees the family's; a private one is yours alone. Viewers read, members
  keep their own, editors change the family's.
- **Everywhere**: a REST API with OpenAPI docs at `/api/docs`, and an MCP server for AI assistants.

## On its own

ioRecipe is a complete recipe book for a family. It needs its database and the Shared ioSuite database; the photos
are kept in the database too, so there is nothing else to back up.

## With the other apps

- **ioStart**: a tile on the start page, and one sign-in for all the apps.
- **ioTask**: a recipe's ingredients go to one of your task lists as a shopping list.

## Install

| | |
| --- | --- |
| Proxmox VE | `bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/iorecipe/proxmox/ct/iorecipe.sh)"` |
| Docker | [docker-compose.yml](https://github.com/avandeputte/iosuite/blob/main/iorecipe/docker-compose.yml): the image `ghcr.io/avandeputte/iosuite/iorecipe` |
| Any Linux or Mac | `git clone https://github.com/avandeputte/iosuite && cd iosuite/iorecipe && ./setup.sh` |
| Port | 8690 |
| Source | [iosuite/iorecipe](https://github.com/avandeputte/iosuite/tree/main/iorecipe) |
