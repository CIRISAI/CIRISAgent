# CIRIS PostgreSQL Setup for Vultr Managed Database

## Quick Start

### 1. Prerequisites (One-time setup in Vultr Console)

#### Create CIRIS User
1. Go to [Vultr Products](https://my.vultr.com/products/) → PostgreSQL → cirispostgres
2. Click **Users** tab
3. Click **Add User**
4. Username: `ciris_user`
5. Password: Generate a strong password (save it securely!)
6. **Important**: Grant `CREATEDB` privilege if available

#### Download SSL Certificate
1. In the same dashboard, go to **Connection Details**
2. Click **Download Signed Certificate**
3. Save as `~/vultr-ca-certificate.crt`

#### Get VPC IP Address
1. In the same dashboard, go to **VPC Network** section
2. Note the VPC IP (format: `10.2.96.X`)
3. This is your internal network IP - use this for production!

### 2. Run Setup Script

```bash
# From the CIRISAgent directory
cd /home/emoore/CIRISAgent

# Run the Vultr setup script
./tools/database/setup_postgresql_vultr.sh \
    ciris_db \
    ciris_user \
    'YOUR_PASSWORD_HERE' \
    10.2.96.X \
    16751 \
    ~/vultr-ca-certificate.crt
```

### 3. Configure Environment

Add to your shell profile (`~/.bashrc` or `~/.zshrc`):

```bash
# Vultr PostgreSQL Connection
export CIRIS_DB_URL='postgresql://ciris_user:YOUR_PASSWORD@10.2.96.X:16751/ciris_db?sslmode=require'
export PGSSLROOTCERT="$HOME/vultr-ca-certificate.crt"
```

Then reload:
```bash
source ~/.bashrc  # or ~/.zshrc
```

### 4. Test Connection

```bash
# Test the connection
psql "$CIRIS_DB_URL"

# Should connect successfully and show:
# psql (14.x, server 18.x)
# SSL connection (protocol: TLSv1.3, ...)
# Type "help" for help.
# ciris_db=>
```

### 5. Run CIRIS

```bash
python main.py --adapter cli --mock-llm
```

## Your Vultr Cluster Details

From your dashboard screenshot:

- **Cluster Name**: cirispostgres
- **Engine**: PostgreSQL v18
- **Location**: Chicago
- **Plan**: Business (4 vCPU, 8192 MB RAM, 160 GB Disk)
- **VPC Subnet**: 10.2.96.0/20
- **Port**: 16751

**Admin User (DO NOT USE for CIRIS)**:
- Username: `vultradmin`
- This is the superuser - create a separate `ciris_user` instead!

**Hosts**:
- **VPC IP**: `10.2.96.X` (internal, recommended for production)
- **Public Host**: `public-vultr-prod-b6ba9a61-7f81-4302-9fd7-62c172fe7368-vultr-pr.vultrdb.com`

## Database Structure

The setup script creates 3 databases:

1. **ciris_db** - Main application database
2. **ciris_db_secrets** - Encrypted secrets storage
3. **ciris_db_auth** - Authentication data

CIRIS automatically uses all three based on the main database name.

## Security Notes

### SSL/TLS
- **Always use SSL**: Connection string includes `?sslmode=require`
- **Certificate**: Stored at `~/vultr-ca-certificate.crt`
- **Never disable SSL** in production!

### Trusted Sources
⚠️ **Important**: Your dashboard shows "cluster is open to all incoming connections"

**Recommended**: Restrict to specific IPs:
1. Go to Vultr dashboard → cirispostgres → **Trusted Sources**
2. Click **Edit**
3. Add only your server IPs
4. Remove `0.0.0.0/0` (all IPs)

### Password Security
- Use a strong password (20+ characters)
- Store in environment variables, not code
- Consider using a secrets manager for production

## Connection Strings

### Main Database (use this)
```bash
postgresql://ciris_user:PASSWORD@10.2.96.X:16751/ciris_db?sslmode=require
```

### Secrets Database (auto-detected by CIRIS)
```bash
postgresql://ciris_user:PASSWORD@10.2.96.X:16751/ciris_db_secrets?sslmode=require
```

### Auth Database (auto-detected by CIRIS)
```bash
postgresql://ciris_user:PASSWORD@10.2.96.X:16751/ciris_db_auth?sslmode=require
```

## Troubleshooting

### "PostgreSQL is not accessible"
- Check VPC IP address is correct
- Verify your machine is on the VPC network
- Check firewall rules in Vultr dashboard

### "Failed to authenticate"
- Verify username is `ciris_user` (not `vultradmin`)
- Check password is correct
- Ensure user was created in Vultr console

### "SSL certificate verify failed"
- Re-download certificate from Vultr dashboard
- Verify `PGSSLROOTCERT` points to correct file
- Check certificate file permissions (should be readable)

### "Permission denied to create database"
- Ensure `ciris_user` has CREATEDB privilege
- May need to grant via vultradmin user:
  ```sql
  ALTER USER ciris_user CREATEDB;
  ```

## Backups

Vultr automatically backs up your database:
- **Frequency**: Check dashboard for schedule
- **Latest Backup**: Shown in dashboard (was "5 minutes ago" at setup)
- **Restore**: Use "Restore From Backup" in dashboard

## Monitoring

Check your cluster status:
- **vCPU Usage**: Dashboard shows real-time usage
- **Network**: Shows bandwidth used
- **Monthly Cost**: $200.00 for your Business plan

## Production Deployment

When deploying CIRIS on production servers:

1. Use VPC IP (not public host)
2. Set environment variables in systemd service or docker-compose
3. Restrict trusted sources to specific IPs
4. Enable automatic backups
5. Monitor connection pool usage
6. Consider read replicas for scaling (add via dashboard)

## Additional Resources

- [Vultr Managed Databases FAQ](https://www.vultr.com/docs/managed-databases-faq/)
- [Vultr Managed Databases Quickstart](https://www.vultr.com/docs/managed-databases-quickstart/)
- CIRIS PostgreSQL Migration: `ciris_engine/logic/persistence/db/migrations/postgres/`
