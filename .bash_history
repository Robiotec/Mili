cd
ls
exit
ls
exit
ls
cd /etc/
ls
cd mavlink-router/
ls
cat main.conf 
cd
cd /var/log/
ls
cd mavlink-router/
ls
cd debug/
ls
clear
ls
cd
cd /var/log/
ls
cd mavlink-router/
ls
cd
cd /etc/
ls
cd mavlink-router/
ls
sudo micro main.conf 
sudo systemctl restart mavlink-router.service 
ifconfig
sudo lsof -i :5760  # TCP antiguo
sudo systemctl stop mavlink-router.service
sudo killall mavlink-routerd
sudo lsof -i :5760  # TCP antiguo
sudo systemctl daemon-reload
sudo systemctl start mavlink-router.service
sudo systemctl status mavlink-router.service
sudo lsof -i :5760  # TCP antiguo
ls
sudo micro main.conf 
sudo systemctl stop mavlink-router.service
sudo kill -9 16081
sudo lsof -i :5760
sudo systemctl start mavlink-router.service
cat main.conf 
ps aux | grep mavlink-routerd
sudo /usr/bin/mavlink-routerd -c /etc/mavlink-router/main.conf -v
sudo systemctl stop mavlink-router.service
sudo killall -9 mavlink-routerd
sudo /usr/bin/mavlink-routerd -c /etc/mavlink-router/main.conf -v
ls
sudo nano main.conf 
sudo /usr/bin/mavlink-routerd -c /etc/mavlink-router/main.conf -v
sudo systemctl daemon-reload 
sudo systemctl start mavlink-router.service 
ls
sudo micro main.conf 
sudo systemctl daemon-reload 
sudo systemctl restart mavlink-router.service 
sudo find /etc -name "*.conf" | grep mavlink
ls
sudo micro main.conf 
sudo systemctl daemon-reload 
sudo systemctl restart mavlink-router.service 
sudo tcpdump -n -i any port 5750 or port 5760 -vv
sudo tcpdump -n -i tailscale0 host 100.125.116.67 and \(port 5760 or port 5750\) -vv
ip a
exit
ls
mkdir -p ~/mediamtx
ls
uname -a
wget https://github.com/bluenviron/mediamtx/releases/download/v1.17.0/mediamtx_v1.17.0_linux_amd64.tar.gz
ls
tar -xzf mediamtx_v1.17.0_linux_amd64.tar.gz 
ls
./mediamtx 
sudo ufw allow 1935/tcp
sudo ufw allow 1935/udp
sudo ufw allow 8554/tcp
sudo ufw allow 8554/udp
sudo ufw reload
cd mediamtx/
ls
./mediamtx 
cd mediamtx/
./mediamtx 
cd mediamtx/
./mediamtx 
cd mediamtx/
./mediamtx 
ls
cd /etc/mavlink-router/
sudo micro main.conf 
sudo nano main.conf 
ls
ping 192.168.30.154
ping 192.168.1.81
ping 100.93.62.24
ping 172.17.0.1
ip a
sudo nano /etc/postgresql/*/main/postgresql.conf
/etc/postgresql/*/main/postgresql.conf
sudo find / -name postgresql.conf 2>/dev/null
sudo find / -name pg_hba.conf 2>/dev/null
psql -U postgres -c "SHOW config_file;"
sudo psql -U postgres -c "SHOW config_file;"
psql -U postgres -c "SHOW hba_file;"
sudo psql -U postgres -c "SHOW hba_file;"
exit
cd
ls
cd mediamtx/
ls
./mediamtx 
cd mediamtx/
./mediamtx 
cd mediamtx/
./mediamtx 
cd mediamtx/
./mediamtx 
cd mediamtx/
ls
./mediamtx 
cd mediamtx/
cd
cd mediamtx/
pwd
cd
sudo nano /etc/systemd/system/mediamtx.service
sudo systemctl daemon-reload 
sudo systemctl enable mediamtx.service 
sudo systemctl start mediamtx.service 
sudo systemctl status mediamtx.service 
sudo systemctl status mavlink-router.service 
ls
sudo tailscale up --advertise-tags=tag:serveruempe --force-reauth
ifconfig
ls
cd mediamtx/
ls
sudo cat mediamtx.yml 
sudo micro mediamtx.yml 
