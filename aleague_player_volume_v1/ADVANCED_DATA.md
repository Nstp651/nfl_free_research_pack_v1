# Advanced Data Layer — V1 Plan

## Why it exists
The basic outcome database (minutes, shots, SoT, saves, team shot environment) is necessary but not sufficient. The edge hypothesis is that A-League player props are mispriced when **current role and attacking opportunity change faster than season averages**.

Advanced data is therefore used to improve *role state and translation*, not to decorate the model with every available metric.

## SkillCorner open A-League sample
The SkillCorner open-data project contains ten 2024/25 A-League matches of broadcast tracking plus Dynamic Events/phases of play, and season-level Physical, Off-Ball Runs and Passing aggregates. It is MIT-licensed.

V1 will use it for feature discovery/calibration only. Candidate feature families:

- final-third/off-ball run frequency;
- runs in behind / target-zone arrival patterns;
- average attacking position / width;
- high-intensity attacking movement;
- possession phase involvement;
- passing/receiving role proxies;
- role similarity between established A-League players and incoming players.

No coefficient may be promoted into production because it looked good on ten matches. Any advanced feature must have a plausible football mechanism and then be validated against the full historical outcome panel or a larger approved source.

## Prior-competition translation
For imports/new players, Layer 1 can research prior-league shots/90, SoT/90, position, starts/minutes, role and advanced context from approved/research sources. V1 records these as a translation prior with explicit uncertainty.

The model will prefer **nearest-role/player analogues** over a single league-wide multiplier. SkillCorner physical/OBR profiles may help define analogues when a comparable player exists in the open aggregate data.

## Current research fields
The research checkpoint should ultimately carry, where available:

- projected minutes low/mean/high;
- start probability;
- position/formation role;
- central-vs-wide attacking deployment;
- striker/wing hierarchy;
- set-piece status;
- teammate competition/absence redistribution;
- recent shots/90 and SoT/90 from canonical data;
- box-touch / shot-map / xG context from research-only sources;
- manager/system change;
- opponent personnel and shape;
- goalkeeper starter confidence;
- import/prior-competition translation receipt.

Fields unavailable from a permitted source remain `UNAVAILABLE`; they are never imputed as zero.
