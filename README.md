# Configure Telegram Bot:
Open Telegram, search for the @BotFather, and type /newbot.

Follow the prompts to name it, and save the provided HTTP API Token safely.

Search for @userinfobot in Telegram and send it a message to get your personal numeric User ID (chat ID).

# Connect Your Google Calendar API Workspace
Go to your GCP Console and search for APIs & Services > Library. Enable the Google Calendar API.

Go to APIs & Services > Credentials and click Create Credentials > Service Account.

Once created, click on the service account email, go to the Keys tab, click Add Key > Create New Key, and select JSON.

This downloads a file to your computer. Rename it exactly to credentials.json and move it into your local travel-bot/ project directory.

Open your personal Google Calendar app in a browser. Create a new calendar for your trip (e.g., "Holland 2026").

Go to its settings, and under Share with specific people, click Add people. Paste the email address of your Service Account (found inside credentials.json) and grant it See all event details access. Copy the Calendar ID from the integration settings page.

# Set up GCS bucket
Navigate to Cloud Storage > Buckets in GCP and click Create.

Name your bucket exactly tulip_assistant. Set its region to match your virtual machine's location (e.g., us-central1).

Click on your newly created bucket, go to the Lifecycle tab, and click Add a Rule.

Set the action to Delete object and the condition to Age: 30 days. This automatically cleans up old conversation logs after your trip.

# Set up the compute instance

Navigate to Compute Engine > VM Instances > Create Instance.
Configure these exact settings to guarantee the server falls within the Always Free baseline limits:
Region: Select us-central1 (Iowa), us-east1 (South Carolina), or us-west1 (Oregon).
Machine configuration: Choose E2 Series, machine type e2-micro (2 vCPU, 1 GB RAM)
Boot Disk: Click Change. Choose Standard Persistent Disk (Ubuntu or Debian Linux), and set the size to 30 GB.
Firewall: Check both Allow HTTP traffic and Allow HTTPS traffic.

Install docker and grand execution permission to your profile

sudo apt-get update && sudo apt-get install -y docker.io
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker $USER

Close the SSH window and reopen it to apply the user group updates.

# CI/CD Pipeline Automation

Add Secrets to GitHub
Create a private GitHub repository for your code. Navigate to Settings > Secrets and variables > Actions, and create three new repository secrets:

GCP_VM_IP: The external IP address of your Compute Engine VM instance.

GCP_VM_USERNAME: Your SSH account connection profile user name (displayed in your VM console terminal).

GCP_SSH_PRIVATE_KEY: Your private SSH key string data (generated on your machine or retrieved from your platform connection profile configuration files).

# Set https and hook up telegram

1. Open an SSH terminal to the machine, and run: ssh -R 80:localhost:80 nokey@localhost.run
2. Look at your terminal screen. It will display a continuous live message block containing a dedicated secure URL ending in .localhost.run
3. Copy that entire https://...localhost.run string to your clipboard. Leave this terminal window running completely undisturbed on your computer so the active line stays up.
4. Open a second, completely separate terminal window on your computer (or use your desktop web browser).
5. Execute this clean network request to clear Telegram's old memory and inject your fresh address (replace the placeholders with your actual Bot Token and the localhost.run link you just generated):
curl -X POST "https://api.telegram.org/bot<YOUR_TELEGRAM_BOT_TOKEN>/setWebhook" \
     -d "url=https://<YOUR_NEW_TUNNEL_SUBDOMAIN>.localhost.run/webhook"
6. If the server mapping handles cleanly, your terminal will instantly echo back this confirmation payload:
{"ok":true,"result":true,"description":"Webhook was set"}

It's possible to create this tunnel once, and keep it running in the background:
ssh -fN -R 80:127.0.0.1:8000 nokey@localhost.run

Get your new address:
ps aux | grep ssh

For killing it, run:
pkill -f "nokey@localhost.run"

# Debug
See logs: docker logs -f --timestamps travel-bot



