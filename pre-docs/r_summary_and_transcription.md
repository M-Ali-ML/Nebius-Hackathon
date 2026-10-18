# Video Summary & Transcription (`r.mov`)

**Presenter:** Dario La Porta (Nebius)  
**Duration:** ~8:56  
**Topic:** Initial configuration, connection, and agent-assisted setup for the **GTC Berlin 2026 Hackathon** Nebius AI Cloud environment.

---

## Summary

### Overview
This walkthrough demonstrates how hackathon participants can join their assigned **Nebius AI Cloud** tenant, navigate the web console, and use a coding agent (such as OpenAI Codex, Claude Code, OpenCode, etc.) paired with the official **Nebius starter skill and participant guide** repository to automate environment verification and workload deployment.

### Key Steps Covered
1. **Accepting the Tenant Invitation (00:00 – 01:20)**
   - Check your email inbox for an invitation from `no-reply@nebius.com` (*"You were invited to join a Nebius tenant"*, e.g., `gtc-berlin-2026-hackathon-68a`).
   - Click **Accept the invitation**, which redirects to `auth.nebius.com`.
   - Sign in using your preferred SSO provider (Google, Microsoft, GitHub, or SSO).

2. **Exploring the Nebius Web Console (01:20 – 02:06)**
   - Once logged in, select your assigned tenant and team project (e.g., `group01-project` in region `uk-south2`).
   - From the console dashboard and left sidebar, you can manage:
     - **Serverless AI:** Jobs, Endpoints, Devlabs
     - **Compute & Orchestration:** Virtual machines, Kubernetes clusters
     - **Storage & Supporting Services:** Object Storage, SecretStash (Cryptography), Container Registry, Observability, Billing, and Administration.

3. **Using the Participant Guide & Starter Skill Repository (02:07 – 03:09)**
   - Repository shown: `https://github.com/dariolaportanebius/nebius-starter-skill` (branch: `hackathon-participant-guide`, file: `README.md`).
   - The `README.md` covers:
     1. **Start here:** Quick-start checklist.
     2. **Join your assigned AI Cloud project:** Accepting invite, verifying region (`uk-south2`), checking `SecretStash` (`hackathon-object-storage`).
     3. **Choose what you need:** Mapping use cases to services (Token Factory for hosted models, Serverless AI Endpoints/Devlabs/Jobs, Compute VMs, Tavily for web search, Object Storage for datasets/checkpoints).
     4. **Know your team's limits:**
        - **Reserved GPU:** 1 NVIDIA RTX PRO 6000 Blackwell Server Edition (`gpu-rtx6000-a` / `1gpu-24vcpu-210gb`)
        - **VM count:** 2 total (including VMs managed by Serverless workloads)
        - **CPU capacity for non-GPU VMs:** 4 vCPUs total
        - **Disks:** 4 total, 500 GiB total network SSD capacity
        - **Public IPv4 addresses:** 1
        - **Container registries:** 1 registry
        - **Object Storage:** 200 GiB standard bucket limit
     5. **Optional CLI & Coding Agent Setup (Section 11):** Instructions designed to be read directly by a coding agent so it can verify your environment, respect team limits, and deploy workloads safely.

4. **Configuring & Verifying the Environment with a Coding Agent (03:10 – 05:43)**
   - In the terminal, the presenter launches **OpenAI Codex** and prompts:
     ```text
     Read in https://github.com/dariolaportanebius/nebius-starter-skill/blob/hackathon-participant-guide/README.md. Follow the Instructions for the agent
     ```
   - The agent fetches the guide, detects the installed `nebius-cloud-basics` skill and `nebius` CLI (`v0.12.290`), and runs read-only checks on the default CLI profile, project ID, region (`uk-south2`), quotas, GPU reservations, and existing workloads.
   - The agent asks the user to confirm whether `group01-project` is their assigned team project. After confirming (`Yes`), setup is marked complete without creating any cloud resources yet.

5. **Deploying a Serverless GPU Endpoint via the Agent (05:44 – 08:14)**
   - The presenter prompts the agent to create a test serverless endpoint:
     ```text
     create a serverless endpoint with the reserver gpu accessible by the user and when used returns the output of nvidia-smi
     ```
   - Using the `nebius-serverless-endpoints` and `nebius-billing` skills, the agent:
     - Estimates the cost (~$1.80/hour or ~$43.32/day).
     - Performs a dry run (`--dry-run`) to validate the configuration (`gpu-rtx6000-a`, `1gpu-24vcpu-210gb`, 50 GiB disk, port 8080, bearer token authentication).
     - Displays the exact `nebius ai endpoint create` command and asks for explicit confirmation before occupying the team's sole GPU.
   - The presenter replies `proceed`.
   - The agent deploys the endpoint (`nvidia-smi`), monitors container initialization, verifies that unauthenticated requests return `HTTP 401` and authenticated requests return `HTTP 200` with live `nvidia-smi` output, and provides the local helper command and stop command.

6. **Verifying the Running Endpoint in the Web UI (08:15 – 08:56)**
   - Switching back to the Nebius web console under **Serverless AI -> Endpoints**, the `nvidia-smi` endpoint is shown as **Running** on `NVIDIA RTX PRO 6000` (`1 GPU, 24 vCPUs, 210 GB`), along with its container settings, public endpoint URL, and logs/metrics tabs.

---

## Full Timestamped Transcription

**[00:00]** *(Screen shows Gmail inbox with an email from Nebius titled "You were invited to join a Nebius tenant" for `gtc-berlin-2026-hackathon-68a`.)*

**[00:03]** **Dario La Porta:** Hello. This video will guide you in the initial configuration and connection to the Nebius Cloud environment, and how to interact with the environment using an agent—in this case, in this example, like Codex.

**[00:21]** So first of all, if you check your inbox, you should be able to see the invitation email to the tenant. In this case, the email should be something similar to the following one. So after you click **Accept the invitation**, you should be able to see something like the following page. Let me show you.

**[00:44]** *(Screen switches to `auth.nebius.com` "Welcome to Nebius" login page.)*

**[00:45]** As you can see, the following page should be the initial connection page where you can log in to Nebius, and you can choose the preferred authentication method. So for instance, if you have a Google account, you can directly click here, **Get started with Google**, and you can single sign-on with your Google account.

**[01:04]** Now, after you sign on, you can access the environment that we configured for the participant. So you should be able to see a page that gives you access to the tenant and your group.

**[01:21]** *(Screen switches to the Nebius AI Cloud console showing `gtc-berlin-2026-hackathon-58e` / `group01-project`.)*

**[01:21]** So in this example, I accessed the tenant that contains your group—in this case, in this example, it is `group01-project`. So as you can see here, you have access to the full web interface, and you can access on the left the different services.

**[01:39]** Now, you can interact through the web UI, or you can also use an agent. We also shared with you a Git repository that contains a guide on how to interact with the interface, with the command line, or using a Codex—so in this example, a Codex agent, or any kind of agent that you want to use. I can show you the guide.

**[02:08]** *(Screen switches to GitHub repository `dariolaportanebius/nebius-starter-skill` on branch `hackathon-participant-guide`.)*

**[02:10]** So as you can see here, this is the shared Git repository that contains the `README` file with all the steps required to sign in to the environment and all the steps that I showed before. So you have the email, and you can accept the invitation and access the environment.

**[02:29]** You have the possibility to follow the guide—so you do it manually, following the steps—or if you go to the bottom part of the page, there is an optional part that gives you the possibility to use an agent.

**[02:45]** *(Scrolls to Section 11: "Optional: set up a coding agent" in the README.)*

**[02:45]** So, you see here: **Set up a coding agent**. So in this case, you can point the agent to this specific section, and the agent can help you in the configuration and access of the environment using the Nebius skills and plugin. Now I will show you in this demo also an example. So if I, for instance, copy this link, now let's move to the terminal.

**[03:10]** *(Screen switches to terminal running OpenAI Codex `v0.102.1`.)*

**[03:13]** Okay, now we are in the Codex terminal, and we can ask Codex to read the `README` file and follow the instructions.

**[03:20]** *(Presenter pastes prompt: `Read in https://github.com/dariolaportanebius/nebius-starter-skill/blob/hackathon-participant-guide/README.md. Follow the Instructions for the agent`)*

**[03:34]** As you can see, the agent is accessing the `README` file.

**[03:51]** It's reading the document. Takes some time to read, interact, and read. And it will print you after it accesses the environment. As you can see, it's detecting that we already have the skill installed, so it can use directly the skill to interact with the environment.

**[04:33]** Yeah, it's detecting that we have the project, it's connected to the project, the command line is configured.

**[04:51]** Yeah, so it's saying that the command line is already configured to interact with the correct group—with the correct project—and the command line meets the skill requirements.

**[05:19]** Yeah, you see here it's printing you all the information that the agent detected.

**[05:29]** *(Agent asks: "Is `group01-project` your assigned team project? That is the remaining detail needed to finalize setup." Presenter types `Yes`.)*

**[05:30]** I can say "Yes" in my case, in my example.

**[05:41]** Okay, so as you can see, the setup is complete. Now, for instance, in my example, I can create a serverless endpoint, and this endpoint can use the reserved GPU, but this will just do a simple `nvidia-smi` when the endpoint is called by the user. So the user can call it, and this will just run `nvidia-smi` from inside the container. Yeah.

**[06:01]** *(Presenter submits prompt: `create a serverless endpoint with the reserver gpu accessible by the user and when used returns the output of nvidia-smi`)*

**[06:15]** As you can see, it's doing the configuration, it's using the skill to interact with the environment.

**[06:36]** Yeah, it's running the command to create the environment.

**[06:46]** Okay. So the agent just verified the possible command doing a dry run. Now the agent is asking me if I want to deploy the configuration.

**[06:58]** *(Presenter types `proceed`.)*

**[07:00]** So, `proceed` to deploy it. Now the agent is executing the command to deploy the environment.

**[08:01]** *(Agent reports that the endpoint is running and verified on the reserved RTX PRO 6000 GPU, returning HTTP 200 with live `nvidia-smi` output.)*

**[08:01]** Okay, now the agent detected that the endpoint is running, and you can access the endpoint also. So I can now show you from the web UI the endpoint.

**[08:15]** *(Screen switches back to the Nebius console under Serverless AI -> Endpoints, showing `nvidia-smi` with status `Running`.)*

**[08:15]** Now let me show you immediately. Endpoint is here. So as you can see in the Serverless section, Endpoints, we have the running endpoint, and we have the information of it. So we can see information regarding the GPU used, and we have also the public endpoint here.

**[08:39]** Now, from here, you can access all the details. Now, everything is possible to execute from the agent—you can ask the agent every question, every information regarding the environment, and you... *(video ends at 08:56)*
