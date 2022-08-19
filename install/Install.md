# Set udev rules

### Allow script running w/o root access
sudo cp 30-bayer.rules /etc/udev/rules.d/

### Add group bayerusb
sudo addgroup bayerusb

### Add user to the group bayerusb
sudo usermod -a -G bayerusb $USER
