<?php

/*
|--------------------------------------------------------------------------
| Application Routes
|--------------------------------------------------------------------------
|
| Here is where you can register all of the routes for an application.
| It's a breeze. Simply tell Laravel the URIs it should respond to
| and give it the controller to call when that URI is requested.
|
*/

Route::get('/login', 'UserController@login');
Route::post('/login', 'UserController@postLogin');


$router->group(['middleware' => ['auth', 'empty_email']], function() {
    Route::get('/logout', 'UserController@logout');

    Route::get('/', 'HomeController@index');
    Route::post('/', 'HomeController@postindex');

    Route::get('/downloads', 'HomeController@downloads');
    Route::post('/downloads', 'HomeController@post_downloads');

    Route::get('/files', 'HomeController@files');
    Route::post('/files', 'HomeController@postfiles');

    Route::get('/public', 'HomeController@public_files');

    Route::get('/files/{id}', 'HomeController@download_id');
    Route::post('/files/{id}', 'HomeController@post_download_id');

    Route::get('downloads/dl', 'HomeController@dl');

    Route::get('user/{username}', 'UserController@user_info');
    Route::post('user/{username}', 'UserController@post_user_info');

    Route::get('user/{username}/password', 'UserController@password');
    Route::post('user/{username}/password', 'UserController@post_password');
});


//Admin's routes
$router->group(['middleware' => 'auth', 'role' => '2'], function() {
    Route::get('/cron', function() {

        if (config('leech.auto_delete')) {
            $time = date("Y-m-d H:i:s", time() - (config('leech.auto_delete_time') * 60 * 60));

            $old_files = DB::table('download_list')
                ->where('date_completed', '<', $time)
                ->where('keep', '=', 0)
                ->get();

            foreach ($old_files as $old_file) {
                $res = @unlink(public_path() . '/' . Config::get('leech.save_to') . '/' . $old_file->id . '_' . $old_file->file_name);
                @unlink(public_path() . '/' . Config::get('leech.save_to') . '/' . $old_file->id . '_' . $old_file->file_name . '.aria2');
                DB::table('download_list')
                    ->where('id', $old_file->id)
                    ->update(['deleted' => 1]);
                if (!$res) echo 'Not deleted: ' . public_path() . '/' . Config::get('leech.save_to') . '/' . $old_file->id . '_' . $old_file->file_name . "\n";
            }

        }
    });

    Route::get('/tools/register', 'UserController@register');
    Route::post('/tools/register', 'UserController@postregister');

    Route::get('/tools/register-csv', 'UserController@register_csv');
    Route::post('/tools/register-csv', 'UserController@postregister_csv');

    Route::get('/tools/users', 'AdminController@users');
    Route::post('/tools/users', 'AdminController@users');

    Route::get('/tools/users/{username}', 'AdminController@user_details');
    Route::post('/tools/users/{username}', 'AdminController@postuser_details');

    Route::get('/tools/users/{username}/credits', 'AdminController@user_details_credits');
    Route::post('/tools/users/{username}/credits', 'AdminController@postuser_details_credits');

    Route::get('/tools/aria2console', 'AdminController@aria2console');
    Route::post('/tools/aria2console', 'AdminController@post_aria2console');

    Route::get('/tools/status', 'AdminController@stat');
    Route::post('/tools/status', 'AdminController@post_stat');
});

Route::controllers([
	'auth' => 'Auth\AuthController',
	'password' => 'Auth\PasswordController',
]);
