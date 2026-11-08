---
name: outreach-tailoring
description: >-
  Use this skill when critiquing a job match from a hiring manager perspective
  or drafting tailored resume bullets and LinkedIn outreach notes.
---

# Outreach and Resume Tailoring Skill

Follow this runbook when generating application assets for top matches.

## Steps

1. **Load Candidate Profile and Job Context**:
   - Call `generate_tailored_outreach_for_job()` with the company, role title, location, and job description.
2. **Run Hiring Manager Objection Check**:
   - Identify the top skepticism a hiring manager will have and write a concrete preemption angle using the candidate's real metrics and degrees.
3. **Draft Bullets and Outreach**:
   - Map 3 resume bullets from `experience_highlights` to the job description.
   - Select the right network hook (`outreach_and_positioning.alumni_and_network_hooks`) based on the job's city and company.
