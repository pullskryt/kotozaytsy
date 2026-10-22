pkgname=kotozaytsy
pkgver=0.1.0
pkgrel=1
pkgdesc='Transparent kitten-bunny desktop pet for Hyprland'
arch=('any')
depends=('python' 'python-gobject' 'python-cairo' 'gtk4' 'gtk4-layer-shell' 'gdk-pixbuf2')
source=('kotozaytsy.py' 'kotobunny.png' 'meow.wav' 'land.wav' 'run.sh')
sha256sums=(            '1f967969eec28bf36005597b0e5d501458af07126e2dac1521c25b9fb88ada0c'
            '96ff5acf115d4963eaada57a3750124ddf9ab860b22089cbfa65e8e7cb8508f1'
            '6b8b2282e9b7644fae2586a8c221c7228f44aa4221798f83adaf2d3b24354c8c'
            '49909aa34fb6232f9ab81424871a4238f5043da4d7e91ca6386e90697982f543'
            '42607a726c74d40e89801077a67551f52641ed6200858794775659502152ee74')

package() {
  install -Dm755 "$srcdir/kotozaytsy.py" "$pkgdir/usr/share/kotozaytsy/kotozaytsy.py"
  install -Dm644 "$srcdir/kotobunny.png" "$pkgdir/usr/share/kotozaytsy/kotobunny.png"
  install -Dm644 "$srcdir/meow.wav" "$pkgdir/usr/share/kotozaytsy/meow.wav"
  install -Dm644 "$srcdir/land.wav" "$pkgdir/usr/share/kotozaytsy/land.wav"
  install -Dm755 "$srcdir/run.sh" "$pkgdir/usr/share/kotozaytsy/run.sh"
  install -d "$pkgdir/usr/bin"
  cat > "$pkgdir/usr/bin/kotozaytsy" <<'EOF'
#!/bin/sh
exec /usr/bin/sh /usr/share/kotozaytsy/run.sh "$@"
EOF
  chmod 755 "$pkgdir/usr/bin/kotozaytsy"
}
