# Emergency Deployment Instructions

> The host this runbook used to name (cirisnode0) was released and now belongs to
> another Vultr customer. Never SSH to an address copied from an old note; take the
> current production host from CIRISBridge.

The automated deployment has failed due to the graceful shutdown timeout issue. Here's how to manually deploy:

## Quick Fix (Recommended)

SSH to the server and run the emergency deployment script:

```bash
ssh <production host>   # see CIRISBridge for the current host
cd /home/ciris/CIRISAgent
./deployment/emergency-deploy.sh
```

This will:
1. Force stop the unresponsive container
2. Deploy any staged container or start fresh
3. Install and start CIRISManager
4. Verify everything is working

## Alternative: Step-by-Step Manual Deployment

If the emergency script is not available:

```bash
# 1. SSH to server
ssh <production host>   # see CIRISBridge for the current host

# 2. Check current state
docker ps -a | grep ciris

# 3. If there's a staged container waiting:
docker stop -t 10 ciris-agent-datum || docker kill ciris-agent-datum
docker rm ciris-agent-datum
docker rename ciris-agent-datum-staged ciris-agent-datum
docker start ciris-agent-datum

# 4. If no staged container, start fresh:
cd /home/ciris/CIRISAgent
git pull origin main
docker-compose -f deployment/docker-compose.dev-prod.yml up -d

# 5. Install CIRISManager
cd /home/ciris/CIRISAgent
python3 -m venv venv
source venv/bin/activate
pip install pyyaml aiofiles

# Create wrapper script
cat > /usr/local/bin/ciris-manager << 'EOF'
#!/bin/bash
cd /home/ciris/CIRISAgent
export PYTHONPATH="/home/ciris/CIRISAgent:$PYTHONPATH"
if [ -d "venv" ]; then
    source venv/bin/activate
fi
python3 -m ciris_manager.cli "$@"
EOF
chmod +x /usr/local/bin/ciris-manager

# 6. Configure and start CIRISManager
mkdir -p /etc/ciris-manager
ciris-manager --generate-config --config /etc/ciris-manager/config.yml
sed -i 's|docker-compose.yml|docker-compose.dev-prod.yml|' /etc/ciris-manager/config.yml

cp deployment/ciris-manager.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable ciris-manager
systemctl start ciris-manager

# 7. Verify
systemctl status ciris-manager
docker ps
curl http://localhost:8080/v1/system/health
```

## Troubleshooting

If the API is still not responding:

1. Check container logs:
   ```bash
   docker logs ciris-agent-datum --tail 100
   ```

2. Check incidents log:
   ```bash
   docker exec ciris-agent-datum tail -n 100 /app/logs/incidents_latest.log
   ```

3. Restart the container:
   ```bash
   docker restart ciris-agent-datum
   ```

4. If all else fails, remove everything and start fresh:
   ```bash
   cd /home/ciris/CIRISAgent
   docker-compose -f deployment/docker-compose.dev-prod.yml down
   docker-compose -f deployment/docker-compose.dev-prod.yml up -d
   ```

## Expected Result

After successful deployment:
- ✅ All containers running (ciris-agent-datum, ciris-gui, ciris-nginx)
- ✅ CIRISManager service active
- ✅ API responding at http://localhost:8080/v1/system/health
- ✅ GUI accessible via nginx

## Next Steps

Once deployed, the next phase is to build the CIRISManager API endpoints for:
- Agent discovery
- Agent creation with WA signatures
- Local auth for update notifications
