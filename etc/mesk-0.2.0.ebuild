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
IUSE="alsa esd gnome mad"

# Runtime deps
RDEPEND=">=dev-lang/python-2.4
	>=x11-libs/gtk+-2.8
	>=dev-python/pygtk-2.8
	=media-libs/gstreamer-0.10*
	=dev-python/gst-python-0.10*
	=media-plugins/gst-plugins-gnomevfs-0.10*
	=media-libs/gst-plugins-good-0.10*
	gnome-base/librsvg
	mad? (=media-plugins/gst-plugins-mad-0.10*
		>=dev-python/eyeD3-0.6.10)
	vorbis? (=media-plugins/gst-plugins-vorbis-0.10*
		=media-plugins/gst-plugins-ogg-0.10*
		>=dev-python/pyvorbis-1.4-r1)
	alsa? (=media-plugins/gst-plugins-alsa-0.10*)
	oss? (=media-plugins/gst-plugins-oss-0.10*)
	esd? (=media-plugins/gst-plugins-esd-0.10*)
	gnome? (=dev-python/gnome-python-2.12*)"
DEPEND="${RDEPEND}
	dev-util/pkgconfig
	dev-util/desktop-file-utils"

src_compile() {
	econf || die
	distutils_src_compile || die
}

src_install() {
	make DESTDIR=${D} install || die
}

pkg_postinst() {
	fdo-mime_mime_database_update
	fdo-mime_desktop_database_update
}
