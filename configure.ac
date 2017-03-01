dnl
dnl  Copyright (C) 2006-2012  Travis Shirk <travis@pobox.com>
dnl
dnl  This program is free software; you can redistribute it and/or modify
dnl  it under the terms of the GNU General Public License as published by
dnl  the Free Software Foundation; either version 2 of the License, or
dnl  (at your option) any later version.
dnl
dnl  This program is distributed in the hope that it will be useful,
dnl  but WITHOUT ANY WARRANTY; without even the implied warranty of
dnl  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
dnl  GNU General Public License for more details.
dnl
dnl  You should have received a copy of the GNU General Public License
dnl  along with this program; if not, write to the Free Software
dnl  Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
dnl
AC_PREREQ([2.59])
AC_INIT([Mesk], [0.3.99], [Travis Shirk <travis@pobox.com>], [mesk])

AC_CONFIG_AUX_DIR([scripts])

PACKAGE_CODENAME="TRUNK"
AC_SUBST([PACKAGE_CODENAME])

EBUILD_RELEASE=
EBUILD_VERSION=${PACKAGE_VERSION}
if test -n "$EBUILD_RELEASE"; then
    EBUILD_VERSION=${EBUILD_VERSION}-${EBUILD_RELEASE}
fi
AC_SUBST([EBUILD_VERSION])

# Expand libdir so it is a full path rather than containing $prefix
AS_AC_EXPAND(INSTALL_PREFIX, $libdir)
AC_SUBST([INSTALL_PREFIX])

AC_COPYRIGHT([GNU GPL])
AC_REVISION([$Revision: 1.12 $])

BUILD_DATE=`date`
AC_SUBST([BUILD_DATE])
MANPAGE_DATE=`date +'%b. %d, %Y'`
AC_SUBST([MANPAGE_DATE])
 
PKG_PROG_PKG_CONFIG([0.19])
AC_PROG_MAKE_SET
AC_PROG_INSTALL
ACX_CHECK_PYTHON([2.7])
ACX_CHECK_EYED3([0.7.0])
PKG_CHECK_MODULES([pygtk], [pygtk-2.0 >= 2.10.0])
PKG_CHECK_MODULES([librsvg], [librsvg-2.0 >= 2.14.0])

sandbox_stub()
{
    return 0
}
GST_INSPECT=gst-inspect-0.10
AC_ARG_ENABLE([sandbox],
              AC_HELP_STRING([--enable-sandbox],
                             [Use this option when running within a sandbox, it will disable gst-inspect tests since they access ${HOME}/.gconfd]),
              if test "$enableval" = "yes"; then
                  echo "YES"
                  GST_INSPECT="sandbox_stub"
              fi
              )

PKG_CHECK_MODULES([gstpython], [gst-python-0.10 >= 0.10.3])
PKG_CHECK_MODULES([gstpython], [gst-python-0.10 >= 0.10.3])
# Check for gstreamer must haves
for element in playbin; do
    AC_MSG_CHECKING([checking for gstreamer ${element} plugin])
    if $GST_INSPECT ${element} > /dev/null 2>&1; then
        AC_MSG_RESULT([yes])
    else
        AC_MSG_RESULT([no])
        AC_MSG_ERROR([Gstreamer plugin ${element} required.])
    fi
done
# Check for gstreamer audio sinks
have_gst_audio_sink=no
for element in alsasink osssink esdsink gconfaudiosink autoaudiosink; do
    AC_MSG_CHECKING([checking for gstreamer ${element} plugin])
    if $GST_INSPECT ${element} > /dev/null 2>&1; then
        have_gst_audio_sink=yes
        AC_MSG_RESULT([yes])
    else
        AC_MSG_RESULT([no])
    fi
done
if test "$have_gst_audio_sink" = "no"; then
    AC_MSG_ERROR([No Gstreamer output plugins found])
fi
# Check gstreamer audio format support
have_gst_audio_format=no
for element in mad ogg vorbisdec cdio; do
    AC_MSG_CHECKING([checking for gstreamer ${element} plugin])
    if $GST_INSPECT ${element} > /dev/null 2>&1; then
        have_gst_audio_format=yes
        eval have_gst_${element}=yes
        AC_MSG_RESULT([yes])
    else
        eval have_gst_${element}=no
        AC_MSG_RESULT([no])
    fi
done
if test "$have_gst_audio_format" = "no"; then
    AC_MSG_ERROR([No Gstreamer audio format plugins found])
fi
# Check gstreamer optionals
for element in gnomevfs; do
    AC_MSG_CHECKING([checking for gstreamer ${element} plugin])
    if $GST_INSPECT ${element} > /dev/null 2>&1; then
        eval have_gst_${element}=yes
        AC_MSG_RESULT([yes])
    else
        eval have_gst_${element}=no
        AC_MSG_RESULT([no])
    fi
done
# mp3 support
HAVE_MP3_SUPPORT="no"
if test "$have_gst_mad" = "yes"; then
    AC_ARG_ENABLE([mp3],
                  AC_HELP_STRING([--disable-mp3],
                                 [disable mp3 support (default auto)]),
                  enable_mp3="$enableval", enable_mp3="yes")
    if test "$enable_mp3" = "yes"; then
        HAVE_MP3_SUPPORT="yes"
    fi
fi
# vorbis support
HAVE_OGGVORBIS_SUPPORT="no"
if test "$have_gst_ogg" = "yes" && test "$have_gst_vorbisdec" = "yes"; then
    AC_ARG_ENABLE([oggvorbis],
                  AC_HELP_STRING([--disable-oggvorbis],
                                 [disable ogg vorbis support (default auto)]),
                  enable_oggvorbis="$enableval", enable_oggvorbis="yes")
    if test "$enable_oggvorbis" = "yes"; then
        # XXX: ogg.vorbis.__version__ (1.2) does not match my install (1.4),
        #      and I don't see a member, no version checking going on
        ACX_CHECK_PYVORBIS
        HAVE_OGGVORBIS_SUPPORT="yes"
    fi
fi
# CD audio support
HAVE_CDROM_SUPPORT="no"
if test "$have_gst_cdio" = "yes"; then
    AC_ARG_ENABLE([cdrom],
                  AC_HELP_STRING([--disable-cdrom],
                                 [disable CDROM support (default auto)]),
                  enable_cdrom="$enableval", enable_cdrom="yes")
    if test "$enable_cdrom" = "yes"; then
        PKG_CHECK_MODULES([hal], [hal >= 0.5.7])
        ACX_CHECK_CDDB_PY([1.4])
        AC_CHECK_PROG([have_eject], [eject], [yes], [no])
        if test "$have_eject" = "no"; then
            AC_MSG_ERROR(
                [The command line util 'eject' is required for CDROM support.])
        fi
        HAVE_CDROM_SUPPORT="yes"
    fi
fi

# Dbus
HAVE_DBUS_SUPPORT="no"
AC_ARG_WITH([dbus],
  AC_HELP_STRING([--without-dbus],
                 [Disable DBus support. Note that CD audio support requires DBus. (default auto)]),
                 enable_dbus="$enableval", enable_dbus="yes")
if test "$enable_dbus" = "yes"; then
    PKG_CHECK_MODULES([dbus], [dbus-1 >= 0.70])
    PKG_CHECK_MODULES([dbusglib], [dbus-glib-1 >= 0.72])
    ACX_CHECK_DBUS_PYTHON([0.70])
    HAVE_DBUS_SUPPORT="yes"
fi
# Without DBus we have not CD support
if test "$HAVE_DBUS_SUPPORT" = "no" -a "$HAVE_CDROM_SUPPORT" = "yes"; then
    AC_MSG_WARN([Disabling CDROM support due to lac of DBus])
    HAVE_CDROM_SUPPORT="no"
fi

# Although the audio formats can cope with not being supported, DBus and CD
# support can be disabled entirely
if test "$HAVE_DBUS_SUPPORT" = "yes"; then
    AC_SUBST([DISABLE_DBUS_SUPPORT], [False])
else
    AC_SUBST([DISABLE_DBUS_SUPPORT], [True])
fi
if test "$HAVE_CDROM_SUPPORT" = "yes" -a "$HAVE_DBUS_SUPPORT" = "yes"; then
    AC_SUBST([DISABLE_CDROM_SUPPORT], [False])
else
    AC_SUBST([DISABLE_CDROM_SUPPORT], [True])
fi

# Done with tests, output files
AC_CONFIG_FILES([Makefile\
                 po/Makefile\
                 setup.py\
		 src/mesk/info.py\
                 scripts/mesk\
                 doc/mesk.1])
if test -f README.in; then
    AC_CONFIG_FILES([README])
fi
if test -f launch.sh.in; then
    AC_CONFIG_FILES([launch.sh])
fi
AC_OUTPUT

if test -f launch.sh; then
    # AC_OUTPUT strips the execute bit
    chmod 755 launch.sh
fi

echo "
***************************************
Mesk Configuration:
   Install path: $prefix
   mp3:          $HAVE_MP3_SUPPORT
   ogg vorbis:   $HAVE_OGGVORBIS_SUPPORT
   CD audio:     $HAVE_CDROM_SUPPORT
   DBus:         $HAVE_DBUS_SUPPORT
***************************************
"
