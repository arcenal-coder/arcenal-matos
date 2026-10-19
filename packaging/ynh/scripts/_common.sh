#!/bin/bash

matos_manage() {
    ynh_exec_as_app "$install_dir/.venv/bin/python" "$install_dir/manage.py" "$@"
}

matos_dependencies() {
    ynh_exec_as_app python3 -m venv "$install_dir/.venv"
    ynh_exec_as_app "$install_dir/.venv/bin/pip" install --disable-pip-version-check -r "$install_dir/requirements.txt"
}

matos_assistance_provision() {
    # Restore may have reset the entire install tree to app:www-data.
    if [ -f "$install_dir/.assistance.json" ]; then
        chown "root:$app" "$install_dir/.assistance.json"
        chmod 640 "$install_dir/.assistance.json"
    fi
    if [ -x /usr/local/sbin/arcenal-assistance-provision ]; then
        /usr/local/sbin/arcenal-assistance-provision
    fi
}

matos_config() {
    main_domain=$(</etc/yunohost/current_host)
    ynh_config_add --template=".env" --destination="$install_dir/.env"
    chown "$app:$app" "$install_dir/.env"
    chmod 400 "$install_dir/.env"
    ynh_config_add_systemd
    ynh_config_add_systemd --service="$app-jobs" --template="jobs.service"
    ynh_config_add --template="jobs.timer" --destination="/etc/systemd/system/$app-jobs.timer"
    systemctl daemon-reload
    matos_assistance_provision
}
