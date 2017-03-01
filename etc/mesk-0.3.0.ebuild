# Copyright 1999-2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header:$

inherit eutils distutils fdo-mime

DESCRIPTION="Mesk is a Gtk+ media player."
HOMEPAGE="http://mesk.nicfit.net/"
SRC_URI="http://mesk.nicfit.net/releases/${P}.tgz"

LICENSE="GPL-2"
SLOT="0"
KEYWORDS="~x86 ~ppc"
IUSE="cdaudio dbus alsa esd oss mad vorbis gnome"

# Runtime deps
RDEPEND=">=dev-lang/python-2.4
	>=dev-python/pygtk-2.10
	>=gnome-base/librsvg-2.14
	>=media-libs/gstreamer-0.10.11
	=dev-python/gst-python-0.10*
	=media-plugins/gst-plugins-gnomevfs-0.10*
	=media-libs/gst-plugins-good-0.10*
	cdaudio? (=media-plugins/gst-plugins-cdio-0.10*
			>=sys-apps/hal-0.5.7
			>=sys-apps/eject-2.1.5
			>=dev-python/cddb-py-1.4)
	dbus? (>=sys-apps/dbus-1.0.0
			>=dev-libs/dbus-glib-0.72
			>=dev-python/dbus-python-0.70)
	mad? (=media-plugins/gst-plugins-mad-0.10*
		>=dev-python/eyeD3-0.6.11)
	vorbis? (=media-plugins/gst-plugins-vorbis-0.10*
		=media-plugins/gst-plugins-ogg-0.10*
		>=dev-python/pyvorbis-1.4)
	alsa? (=media-plugins/gst-plugins-alsa-0.10*)
	oss? (=media-plugins/gst-plugins-oss-0.10*)
	esd? (=media-plugins/gst-plugins-esd-0.10*)
	gnome? (=dev-python/gnome-python-2.16*)"
DEPEND="${RDEPEND}
	dev-util/pkgconfig
	dev-util/desktop-file-utils"

src_compile() {
	econf --enable-sandbox \
	$(use_enable mad mp3) \
	$(use_enable vorbis oggvorbis) \
	$(use_enable cdaudio cdrom) \
	$(use_with dbus dbus) \
	|| die "Error: econf failed!"
	distutils_src_compile || die

	make DESTDIR=${D} all || die
}

src_install() {
	make DESTDIR=${D} install || die
}

pkg_postinst() {
	python_version
	python_mod_optimize ${ROOT}usr/lib/python${PYVER}/site-packages/mesk

	fdo-mime_mime_database_update
	fdo-mime_desktop_database_update
}

pkg_postrm() {
	python_version
	python_mod_cleanup ${ROOT}usr/lib/python${PYVER}/site-packages/mesk
}
